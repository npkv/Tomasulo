# issue.py
# ISSUE stage (also fetch and decode): up to 'issue width' instructions per
# cycle, strictly in program order.
#
# Original (Qing, 2017): fetched exactly one instruction per cycle and stopped
# fetching after a Bne until it resolved (no prediction).
#
# Changes for this assignment:
#   - a loop issues up to cfg.issue_width (1..4) instructions per cycle; the
#     group stops at the first instruction that cannot be issued (ROB full,
#     reservation station full, load/store queue full), so issue stays in order
#   - every instruction in the group sees the RAT updates of the earlier ones
#     in the same group (renaming inside the issue group)
#   - branches are predicted with the 8-entry BTB / 1-bit predictor; a
#     predicted-taken branch ends the issue group and fetch continues at the
#     predicted target in the next cycle
#   - fetch is held after a misprediction until m.fetch_resume (cycle n+2)
#   - Beq added; Sub, Sub.d handled; R0 is never renamed

from init import ROBEntry, RSEntry, LSQEntry, Operand

RS_OF = {'Add': 'int', 'Addi': 'int', 'Sub': 'int', 'Beq': 'int', 'Bne': 'int',
         'Add.d': 'fpadd', 'Sub.d': 'fpadd', 'Mult.d': 'fpmul'}


def read_operand(m, reg):
    """Rename one source register: value from the register file, value from a
    finished ROB entry, or the tag of the ROB entry that will produce it."""
    kind, n = reg
    if kind == 'R' and n == 0:
        return Operand(value=0, avail=0)
    producer = m.rat[kind][n]
    if producer is None:
        return Operand(value=m.reg[kind][n], avail=0)
    if producer.wb is not None:                     # already broadcast, value sits in the ROB
        return Operand(value=producer.value, avail=producer.wb)
    return Operand(tag=producer)


def free_rs(m, kind):
    for e in m.rs[kind]:
        if not e.busy:
            return e
    return None


def issue_one(m, ins, cycle):
    """Try to issue one instruction.  Returns the ROB entry, or None on a
    structural stall."""
    cfg = m.cfg
    if len(m.rob) >= cfg.rob_size:
        return None
    if ins.op in ('Ld', 'Sd'):
        if len(m.lsq) >= cfg.rs['ldst']:
            return None
        rs_entry = None
    else:
        rs_entry = free_rs(m, RS_OF[ins.op])
        if rs_entry is None:
            return None

    rob = ROBEntry(m.next_seq, m.next_slot, ins, cycle)
    m.next_seq += 1
    m.next_slot = (m.next_slot + 1) % cfg.rob_size

    # read / rename sources BEFORE the destination is renamed
    # (Add R1, R1, R2 must read the old R1)
    if ins.op == 'Ld':
        base = read_operand(m, ins.srcs[0])
        m.lsq.append(LSQEntry(rob, 'Ld', base, ins.imm, None))
    elif ins.op == 'Sd':
        base = read_operand(m, ins.srcs[0])
        data = read_operand(m, ins.srcs[1])
        m.lsq.append(LSQEntry(rob, 'Sd', base, ins.imm, data))
    else:
        rs_entry.busy = True
        rs_entry.op = ins.op
        rs_entry.rob = rob
        rs_entry.src1 = read_operand(m, ins.srcs[0])
        if ins.op == 'Addi':
            rs_entry.src2 = Operand(value=ins.imm, avail=0)
        else:
            rs_entry.src2 = read_operand(m, ins.srcs[1])

    # rename the destination
    if ins.dest is not None and ins.dest != ('R', 0):
        m.rat[ins.dest[0]][ins.dest[1]] = rob

    m.rob.append(rob)
    return rob


def issue(m, cycle):
    if cycle < m.fetch_resume:
        return
    issued = 0
    while issued < m.cfg.issue_width and 0 <= m.pc < len(m.program):
        ins = m.program[m.pc]
        rob = issue_one(m, ins, cycle)
        if rob is None:                         # structural hazard: stop, stay in order
            m.note(cycle, 'ISSUE stall at "%s" (ROB/RS/LSQ full)' % ins.text)
            break
        issued += 1
        m.note(cycle, 'ISSUE %s -> %s' % (ins.text, rob.name))
        if ins.op in ('Beq', 'Bne'):
            taken, target = m.btb.predict(m.pc)
            rob.pred_taken = taken
            rob.pred_target = target
            m.note(cycle, '      predicted %s' % ('taken -> %d' % (target * 4) if taken else 'not taken'))
            m.pc = target
            if taken:                           # fetch redirect ends this issue group
                break
        else:
            m.pc += 1
