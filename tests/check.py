#!/usr/bin/env python3
# check.py - automatic correctness check of the multi-issue simulator.
#
# For every test file given (default: all tests/*.txt) and every issue width
# 1..4 it runs the simulator and verifies:
#
#   functional
#     F1  committed instruction sequence == sequential reference interpreter
#     F2  final integer / FP registers   == reference
#     F3  final memory                   == reference
#   timing / structural
#     T1  issue is in program order, at most <issue width> per cycle
#         (wrong-path instructions included)
#     T2  commit is in program order, at most <commit width> per cycle
#     T3  EX starts after ISSUE and lasts exactly the configured EX cycles
#     T4  WB after EX (ALU) / after MEM (loads); MEM after EX; COMMIT after WB
#         (branches: after EX; stores: after EX)
#     T5  RAW: an instruction starts EX only after every producer's WB
#         (store data: commit after the producer's WB)
#     T6  at most <CDB width> broadcasts per cycle
#     T7  memory port: load accesses and store writes never overlap
#     T8  unpipelined integer adder: never more than <# of FUs> busy;
#         pipelined units: at most <# of FUs> starts per cycle
#     T9  after a misprediction resolved in cycle n the next instruction
#         is issued in cycle n+2 or later
#     T10 loads: forwarded value only when an older store to the same
#         address is still queued or still writing memory when the load reads
#
# Usage:  python3 tests/check.py [test files...]

import glob
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'code'))

from config import read_input                      # noqa: E402
from main import simulate                          # noqa: E402
from reference import run_reference                # noqa: E402


def check(path, width):
    cfg, program = read_input(path)
    cfg.issue_width = width
    cfg.finish()
    m, truncated = simulate(cfg, program, max_cycles=20000)
    errors = []
    if truncated:
        return ['did not finish (use a terminating program)'], m

    ref_reg, ref_mem, ref_trace, _ = run_reference(cfg, program)
    fin = m.finished
    # F1-F3
    if [e.ins.index for e in fin] != ref_trace:
        errors.append('F1 committed sequence differs from reference')
    for kind in 'RF':
        for i in range(32):
            if m.reg[kind][i] != ref_reg[kind][i]:
                errors.append('F2 %s%d = %r, reference %r' % (kind, i, m.reg[kind][i], ref_reg[kind][i]))
    for a in range(cfg.mem_bytes):
        if m.memory[a] != ref_mem[a]:
            errors.append('F3 Mem[%d] = %r, reference %r' % (a, m.memory[a], ref_mem[a]))

    every = sorted(fin + m.squashed, key=lambda e: e.seq)
    # T1
    for a, b in zip(every, every[1:]):
        if b.issue < a.issue:
            errors.append('T1 issue out of order: %s' % b.ins.text)
    for c, n in Counter(e.issue for e in every).items():
        if n > cfg.issue_width:
            errors.append('T1 %d issued in cycle %d' % (n, c))
    # T2
    for a, b in zip(fin, fin[1:]):
        if b.commit < a.commit or b.seq < a.seq:
            errors.append('T2 commit out of order: %s' % b.ins.text)
    for c, n in Counter(e.commit for e in fin).items():
        if n > cfg.commit_width:
            errors.append('T2 %d committed in cycle %d' % (n, c))

    lat = {'Add': cfg.ex['int'], 'Addi': cfg.ex['int'], 'Sub': cfg.ex['int'],
           'Beq': cfg.ex['int'], 'Bne': cfg.ex['int'], 'Add.d': cfg.ex['fpadd'],
           'Sub.d': cfg.ex['fpadd'], 'Mult.d': cfg.ex['fpmul'],
           'Ld': cfg.ex['ldst'], 'Sd': cfg.ex['ldst']}
    for e in fin:
        op = e.ins.op
        t = e.ins.text
        # T3
        if e.ex is None or e.ex[0] <= e.issue or e.ex[1] - e.ex[0] + 1 != lat[op]:
            errors.append('T3 bad EX %s for %s (issue %d)' % (e.ex, t, e.issue))
            continue
        # T4
        if op in ('Beq', 'Bne'):
            if e.commit <= e.ex[1] or e.wb is not None:
                errors.append('T4 branch %s' % t)
        elif op == 'Sd':
            if e.commit <= e.ex[1] or e.mem is None or e.mem[0] != e.commit:
                errors.append('T4 store %s' % t)
        elif op == 'Ld':
            if e.mem is None or e.mem[0] <= e.ex[1] or e.wb <= e.mem[1] or e.commit <= e.wb:
                errors.append('T4 load %s' % t)
            exp = 1 if e.forwarded else cfg.mem_cycles
            if e.mem and e.mem[1] - e.mem[0] + 1 != exp:
                errors.append('T4 load MEM length %s' % t)
        else:
            if e.wb is None or e.wb <= e.ex[1] or e.commit <= e.wb:
                errors.append('T4 %s' % t)

    # T5: producers in committed order
    last_writer = {}
    for e in fin:
        op = e.ins.op
        for k, src in enumerate(e.ins.srcs):
            if src == ('R', 0):
                continue
            p = last_writer.get(src)
            if p is None:
                continue
            if op == 'Sd' and k == 1:              # store data
                if e.commit <= p.wb:
                    errors.append('T5 store data before producer WB: %s' % e.ins.text)
            elif e.ex[0] <= p.wb:
                errors.append('T5 %s starts EX in %d, producer %s WB %d'
                              % (e.ins.text, e.ex[0], p.ins.text, p.wb))
        if e.dest is not None and e.dest != ('R', 0):
            last_writer[e.dest] = e
    # T6
    for c, n in Counter(e.wb for e in every if e.wb is not None).items():
        if n > cfg.cdb_width:
            errors.append('T6 %d broadcasts in cycle %d' % (n, c))
    # T7
    busy = Counter()
    for e in every:
        if e.mem is None or e.forwarded:
            continue
        if e.ins.op == 'Ld' and e.squashed:
            continue                                # cut short by the squash
        for c in range(e.mem[0], e.mem[1] + 1):
            busy[c] += 1
    for c, n in busy.items():
        if n > 1:
            errors.append('T7 memory port used %d times in cycle %d' % (n, c))
    # T8
    int_busy = Counter()
    starts = Counter()
    for e in fin:                                  # squashed ones may be cut short
        op = e.ins.op
        if lat[op] and op in ('Add', 'Addi', 'Sub', 'Beq', 'Bne'):
            for c in range(e.ex[0], e.ex[1] + 1):
                int_busy[c] += 1
        elif op in ('Add.d', 'Sub.d'):
            starts[('fpadd', e.ex[0])] += 1
        elif op == 'Mult.d':
            starts[('fpmul', e.ex[0])] += 1
        else:
            starts[('ldst', e.ex[0])] += 1
    for c, n in int_busy.items():
        if n > cfg.fus['int']:
            errors.append('T8 %d integer adders busy in cycle %d' % (n, c))
    for (k, c), n in starts.items():
        if n > cfg.fus[k]:
            errors.append('T8 %d %s starts in cycle %d' % (n, k, c))
    # T9
    for b in fin:
        if b.mispredicted:
            nxt = [e for e in every if e.seq > b.seq and not e.squashed]
            if nxt and nxt[0].issue < b.ex[1] + 2:
                errors.append('T9 fetch after misprediction too early: %s' % nxt[0].ins.text)
    # T10
    for i, e in enumerate(fin):
        if e.ins.op == 'Ld' and e.forwarded:
            ok = any(s.ins.op == 'Sd' and s.seq < e.seq and s.mem[1] >= e.mem[0] for s in fin[:i])
            if not ok:
                errors.append('T10 forwarded load without pending store: %s' % e.ins.text)
    return errors, m


def main():
    files = sys.argv[1:] or sorted(glob.glob(os.path.join(HERE, '*.txt')))
    bad = 0
    for f in files:
        name = os.path.basename(f)
        if name == 'spec_sample.txt':          # infinite loop by design
            continue
        for w in (1, 2, 3, 4):
            errors, m = check(f, w)
            n = len(m.finished)
            last = m.finished[-1].commit if m.finished else 0
            status = 'PASS' if not errors else 'FAIL'
            print('%-28s width %d  %-4s  %4d instr  %4d cycles  IPC %.2f  mispred %d  squashed %d'
                  % (name, w, status, n, last, n / last if last else 0,
                     m.stats['mispredictions'], len(m.squashed)))
            for e in errors[:10]:
                print('      ' + e)
            bad += bool(errors)
    print('\n%s' % ('ALL CHECKS PASSED' if not bad else '%d FAILED RUNS' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
