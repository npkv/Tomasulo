# commit.py
# COMMIT stage: retire up to cfg.commit_width instructions per cycle from the
# head of the ROB, in program order.
#
#   - ALU instructions and loads commit at the earliest in the cycle after
#     their CDB broadcast; the value is written to the register file and the
#     RAT entry is cleared if it still points at this ROB entry.
#   - Branches commit at the earliest in the cycle after their last EX cycle
#     (they do not use the CDB).
#   - Stores commit when their address and data are known and the memory port
#     is free; the store writes memory in the commit stage, occupying the port
#     for "Cycles in Mem" cycles (shown in the MEM column), and leaves the
#     load/store queue.
#
# Original (Qing, 2017): committed at most one entry (two in a special store
# case), printed the entry, and had no notion of commit width.

class SimulationError(Exception):
    pass


def can_commit(m, h, cycle):
    op = h.ins.op
    if op in ('Beq', 'Bne'):
        return h.ex is not None and h.ex[1] < cycle
    if op == 'Sd':
        q = next(q for q in m.lsq if q.rob is h)
        return (q.addr_cycle is not None and q.addr_cycle < cycle
                and q.data.ready(cycle) and m.mem_busy_until < cycle)
    return h.wb is not None and h.wb < cycle


def commit(m, cycle):
    done = 0
    while done < m.cfg.commit_width and m.rob:
        h = m.rob[0]
        if not can_commit(m, h, cycle):
            break
        if h.fault:
            raise SimulationError('cycle %d: %s: %s' % (cycle, h.ins.text, h.fault))
        if h.ins.op == 'Sd':
            q = next(q for q in m.lsq if q.rob is h)
            if not 0 <= q.address < m.cfg.mem_bytes:
                raise SimulationError('cycle %d: %s: store to invalid address %d'
                                      % (cycle, h.ins.text, q.address))
            m.memory[q.address] = q.data.value
            last = cycle + m.cfg.mem_cycles - 1
            h.mem = (cycle, last)
            m.mem_busy_until = last
            m.mem_user = None           # port now belongs to this (committed) store
            m.lsq.remove(q)             # dequeued at commit ...
            m.writing.append((q, last))  # ... but forwardable until the write is done
            m.note(cycle, 'COMMIT %s writes Mem[%d] = %r' % (h.ins.text, q.address, q.data.value))
        else:
            if h.dest is not None and h.dest != ('R', 0):
                kind, n = h.dest
                m.reg[kind][n] = h.value
                if m.rat[kind][n] is h:
                    m.rat[kind][n] = None
            m.note(cycle, 'COMMIT %s (%s)' % (h.ins.text, h.name))
        h.commit = cycle
        m.finished.append(h)
        m.rob.popleft()
        done += 1
