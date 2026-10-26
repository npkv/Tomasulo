# exe.py
# EX stage.
#
#   - ALU instructions leave their reservation station when they start
#     executing; the result is ready for the CDB in the cycle after the last
#     EX cycle.
#   - Integer adder: unpipelined.  FP adder / FP multiplier: pipelined.
#     The number of units of each kind comes from the input file.
#   - Branches execute on the integer adder and are resolved at the end of
#     their (last) EX cycle; the resolution is handled by squash.py at the end
#     of that cycle.
#   - Loads / stores compute their effective address on the dedicated
#     (pipelined) address adder; they stay in the load/store queue.
#
# Original (Qing, 2017): one instruction per RS group per cycle, the oldest
# was not preferred, the integer adder was pipelined, there was one unit of
# each kind and the FU entry was advanced twice in some cycles (the sample
# report had to add a call-history workaround for that).  Here every unit
# kind can start up to "# of FUs" operations per cycle (unpipelined units: as
# many as are free), always choosing the oldest ready instruction first, and
# timing is kept with explicit start / end cycles instead of per-cycle
# counters, so an operation can never be advanced twice.

from init import InFlight, PendingResult


def alu(op, a, b):
    if op in ('Add', 'Addi'):
        return int(a) + int(b)
    if op == 'Sub':
        return int(a) - int(b)
    if op == 'Add.d':
        return float(a) + float(b)
    if op == 'Sub.d':
        return float(a) - float(b)
    if op == 'Mult.d':
        return float(a) * float(b)
    raise ValueError(op)


def dispatch_rs(m, kind, cycle):
    pool = m.fu[kind]
    ready = sorted((e for e in m.rs[kind] if e.ready(cycle)), key=lambda e: e.rob.seq)
    for e in ready:
        if not pool.can_start(cycle):
            break
        unit = pool.start(cycle)
        rob = e.rob
        last = cycle + pool.latency - 1
        rob.ex = (cycle, last)
        a, b = e.src1.value, e.src2.value
        if e.op in ('Beq', 'Bne'):
            rob.taken = (a == b) if e.op == 'Beq' else (a != b)
            rob.target = rob.ins.index + 1 + rob.ins.imm     # PC + 4 + offset << 2, in words
            m.resolutions.append(rob)                       # resolved at the end of 'last'
            value = None
        else:
            value = alu(e.op, a, b)
            m.results.append(PendingResult(rob, value, last + 1))
        m.in_flight.append(InFlight(rob, pool, unit, value, last))
        m.note(cycle, 'EX start %s (%s), last EX cycle %d' % (rob.ins.text, rob.name, last))
        e.busy = False                                      # RS entry is free again


def dispatch_address(m, cycle):
    pool = m.fu['addr']
    for q in m.lsq:                                         # program order = oldest first
        if not pool.can_start(cycle):
            break
        if q.addr_started or not q.base.ready(cycle) or q.rob.issue >= cycle:
            continue
        pool.start(cycle)
        q.addr_started = True
        q.address = int(q.base.value) + q.imm
        q.addr_cycle = cycle + pool.latency - 1
        q.rob.ex = (cycle, q.addr_cycle)
        m.note(cycle, 'EX start %s address = %d' % (q.rob.ins.text, q.address))


def exe(m, cycle):
    # retire finished in-flight bookkeeping
    m.in_flight = [f for f in m.in_flight if f.last_cycle >= cycle]
    dispatch_address(m, cycle)
    for kind in ('int', 'fpadd', 'fpmul'):
        dispatch_rs(m, kind, cycle)
