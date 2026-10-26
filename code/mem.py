# mem.py
# MEM stage for loads (stores write memory at COMMIT, see commit.py).
#
# A load whose address was computed in an earlier cycle:
#   1. waits while any older store in the load/store queue still has an
#      unknown address (memory disambiguation: the load cannot be sure it is
#      independent of that store);
#   2. if the youngest older store with the same address is found, the value
#      is forwarded from that store (1 cycle) as soon as the store's data is
#      available.  A store that has committed but is still writing memory
#      (port busy) can still forward - it sits in a small write buffer;
#   3. otherwise it reads memory: single port, not pipelined, "Cycles in Mem"
#      cycles.  A store being written at commit also occupies the port.
# The load's queue entry is freed once its value has been obtained.  Loads
# may go to memory out of order with respect to each other (oldest first when
# several are ready).
#
# Original (Qing, 2017): the forwarding check only looked at the nearest older
# store; stores were sent to memory before they committed because
# check_if_sd_committable was referenced but never called (and used a field
# name that does not exist); the "has data" test looked at queue entry 0
# instead of the load being examined.  All three are fixed here.

from init import PendingResult


def valid_address(m, addr):
    return 0 <= addr < m.cfg.mem_bytes


def mem(m, cycle):
    # free the queue entries of loads that already have their value
    m.lsq = [q for q in m.lsq if not (q.op == 'Ld' and q.done_cycle is not None
                                      and q.done_cycle < cycle)]
    if m.mem_user is not None and m.mem_busy_until < cycle:
        m.mem_user = None
    m.writing = [(q, last) for q, last in m.writing if last >= cycle]
    writing = [q for q, last in m.writing]         # committed, all older than any queued load

    for q in m.lsq:
        if q.op != 'Ld' or q.mem_started or q.addr_cycle is None or q.addr_cycle >= cycle:
            continue
        rob = q.rob
        older_stores = [s for s in m.lsq if s.op == 'Sd' and s.rob.seq < rob.seq]
        if any(s.addr_cycle is None or s.addr_cycle >= cycle for s in older_stores):
            continue                                    # unresolved store address: wait
        match = None
        for s in writing + older_stores:                # youngest older store with same address
            if s.address == q.address:
                match = s
        if match is not None:
            if not match.data.ready(cycle):
                continue                                # store data not there yet
            q.mem_started = True
            q.done_cycle = cycle
            rob.mem = (cycle, cycle)                    # forwarding takes 1 cycle
            rob.forwarded = True
            m.results.append(PendingResult(rob, match.data.value, cycle + 1))
            m.note(cycle, 'MEM %s forwarded %r from %s' % (rob.ins.text, match.data.value, match.rob.name))
            continue
        if m.mem_busy_until >= cycle:
            continue                                    # memory port busy
        last = cycle + m.cfg.mem_cycles - 1
        if valid_address(m, q.address):
            value = m.memory[q.address]
        else:
            value = 0.0
            rob.fault = 'load from invalid address %d' % q.address
        q.mem_started = True
        q.done_cycle = last
        rob.mem = (cycle, last)
        m.mem_busy_until = last
        m.mem_user = rob
        m.results.append(PendingResult(rob, value, last + 1))
        m.note(cycle, 'MEM %s reads Mem[%d], cycles %d-%d' % (rob.ins.text, q.address, cycle, last))
