# wb.py
# WB stage: broadcast finished results on the CDB.
#
# Original (Qing, 2017): one result per cycle, and the broadcast wrote the
# value into the RAT for the destination register even when a younger
# instruction had already renamed that register again - the younger
# instruction's consumers then read a stale value.
#
# Now:
#   - up to cfg.cdb_width results per cycle (default = issue width; set
#     "CDB width = 1" in the input file for a single CDB), oldest first
#   - the value goes to the ROB entry and to every waiting reservation station
#     and load/store queue operand; the RAT is not written (a RAT entry points
#     at a ROB entry, and a source that maps to a finished ROB entry reads the
#     value from the ROB at issue), so the stale-value bug cannot happen.


def broadcast(m, rob, value, cycle):
    rob.value = value
    rob.wb = cycle
    for kind in m.rs:
        for e in m.rs[kind]:
            if not e.busy:
                continue
            for opnd in (e.src1, e.src2):
                if opnd.tag is rob:
                    opnd.tag, opnd.value, opnd.avail = None, value, cycle
    for q in m.lsq:
        for opnd in (q.base, q.data):
            if opnd is not None and opnd.tag is rob:
                opnd.tag, opnd.value, opnd.avail = None, value, cycle


def wb(m, cycle):
    ready = sorted((r for r in m.results if r.ready_cycle <= cycle), key=lambda r: r.rob.seq)
    for r in ready[:m.cfg.cdb_width]:
        broadcast(m, r.rob, r.value, cycle)
        m.results.remove(r)
        m.note(cycle, 'WB  %s (%s) = %r' % (r.rob.ins.text, r.rob.name, r.value))
