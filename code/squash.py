# squash.py  (new)
# Branch resolution and misprediction recovery, done at the end of a cycle.
#
# A branch is resolved at the end of its last EX cycle n.  The BTB / 1-bit
# predictor is updated with the real outcome.  On a misprediction:
#   1. every ROB entry younger than the branch is removed (ROB entries that
#      "surpass the branch")
#   2. their reservation stations, load/store queue entries, pending CDB
#      results and functional units are released ("clear the reservation
#      station's wait-for tag fields for wrong instructions")
#   3. the RAT is recovered: it is rebuilt from the ROB entries that remain
#      (older than the branch): each register maps to the youngest remaining
#      ROB entry that writes it, otherwise to the register file
#   4. fetch is redirected to the correct path.  The recovery takes one cycle
#      (n+1) and fetching from the correct instruction starts in cycle n+2.
# If several branches resolve in the same cycle the oldest mispredicted one is
# handled; the younger ones are squashed by it.


def resolve_branches(m, cycle):
    now = sorted((b for b in m.resolutions if b.ex[1] == cycle), key=lambda b: b.seq)
    m.resolutions = [b for b in m.resolutions if b.ex[1] != cycle]
    for b in now:
        if b.squashed:
            continue
        m.stats['branches'] += 1
        m.btb.update(b.ins.index, b.taken, b.target)
        correct_next = b.target if b.taken else b.ins.index + 1
        predicted_next = b.pred_target if b.pred_taken else b.ins.index + 1
        if correct_next == predicted_next:
            m.note(cycle, 'BRANCH %s resolved %s, prediction correct'
                   % (b.ins.text, 'taken' if b.taken else 'not taken'))
            continue
        b.mispredicted = True
        m.stats['mispredictions'] += 1
        m.note(cycle, 'BRANCH %s resolved %s, MISPREDICTED -> squash, fetch from %d in cycle %d'
               % (b.ins.text, 'taken' if b.taken else 'not taken', correct_next * 4, cycle + 2))
        squash_younger(m, b, cycle)
        m.pc = correct_next
        m.fetch_resume = cycle + 2


def squash_younger(m, branch, cycle):
    victims = [e for e in m.rob if e.seq > branch.seq]
    if not victims:
        return
    dead = set(id(e) for e in victims)
    for e in victims:
        e.squashed = True
        m.squashed.append(e)
    # ROB
    while m.rob and m.rob[-1].seq > branch.seq:
        m.rob.pop()
    # reservation stations
    for kind in m.rs:
        for e in m.rs[kind]:
            if e.busy and id(e.rob) in dead:
                e.busy = False
    # load/store queue (and the memory port if a wrong-path load holds it)
    m.lsq = [q for q in m.lsq if id(q.rob) not in dead]
    if m.mem_user is not None and id(m.mem_user) in dead:
        m.mem_busy_until = min(m.mem_busy_until, cycle)
        m.mem_user = None
    # functional units and results waiting for the CDB
    for f in m.in_flight:
        if id(f.rob) in dead:
            f.pool.release(f.unit, cycle)
    m.in_flight = [f for f in m.in_flight if id(f.rob) not in dead]
    m.results = [r for r in m.results if id(r.rob) not in dead]
    m.resolutions = [b for b in m.resolutions if id(b) not in dead]
    # RAT recovery
    for kind in m.rat:
        m.rat[kind] = [None] * 32
    for e in m.rob:
        if e.dest is not None and e.dest != ('R', 0):
            m.rat[e.dest[0]][e.dest[1]] = e
    # ROB slot numbering continues after the branch
    m.next_slot = (branch.slot + 1) % m.cfg.rob_size
