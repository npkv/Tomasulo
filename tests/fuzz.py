#!/usr/bin/env python3
# fuzz.py - random stress test.  Generates random programs (ALU ops, loads and
# stores to a few overlapping addresses, forward branches, one counted loop)
# and random hardware configurations, then runs every check of check.py with
# issue width 1..4.  Usage: python3 tests/fuzz.py [number of programs] [seed]

import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check import check          # noqa: E402


def random_program(rng):
    lines = []
    n = rng.randint(6, 22)
    body = []
    for i in range(n):
        k = rng.random()
        r = lambda: 'R%d' % rng.randint(0, 6)          # noqa: E731
        f = lambda: 'F%d' % rng.randint(0, 6)          # noqa: E731
        if k < 0.15:
            body.append('Add %s, %s, %s' % (r(), r(), r()))
        elif k < 0.25:
            body.append('Sub %s, %s, %s' % (r(), r(), r()))
        elif k < 0.35:
            body.append('Addi %s, %s, %d' % (r(), r(), rng.randint(-3, 3)))
        elif k < 0.47:
            body.append('Add.d %s, %s, %s' % (f(), f(), f()))
        elif k < 0.55:
            body.append('Sub.d %s, %s, %s' % (f(), f(), f()))
        elif k < 0.63:
            body.append('Mult.d %s, %s, %s' % (f(), f(), f()))
        elif k < 0.76:
            body.append('Ld %s, %d(R0)' % (f(), rng.choice([0, 4, 8, 12])))
        elif k < 0.88:
            body.append('Sd %s, %d(R0)' % (f(), rng.choice([0, 4, 8, 12])))
        else:
            remaining = n - i - 1
            off = rng.randint(0, max(0, remaining))
            body.append('%s %s, %s, %d' % (rng.choice(['Beq', 'Bne']), r(), r(), off))
    # wrap the body in a counted loop on R7 (never written by the body)
    loops = rng.randint(1, 3)
    prog = ['Addi R7, R0, %d' % loops] + body + ['Addi R7, R7, -1',
                                                'Bne R7, R0, %d' % (-(len(body) + 2))]
    return prog


def random_config(rng, prog):
    cfg = []
    cfg.append('Integer adder %d %d %d' % (rng.randint(1, 4), rng.randint(1, 3), rng.randint(1, 2)))
    cfg.append('FP adder %d %d %d' % (rng.randint(1, 4), rng.randint(1, 4), rng.randint(1, 2)))
    cfg.append('FP multiplier %d %d %d' % (rng.randint(1, 3), rng.randint(1, 10), rng.randint(1, 2)))
    cfg.append('Load/store unit %d %d %d %d' % (rng.randint(1, 5), rng.randint(1, 2),
                                                rng.randint(1, 6), rng.randint(1, 2)))
    cfg.append('ROB entries = %d' % rng.randint(2, 32))
    cfg.append('R1=%d, R2=%d, R3=%d, F1=%.1f, F2=%.1f, F3=%.1f' % (
        rng.randint(-2, 2), rng.randint(-2, 2), rng.randint(0, 3),
        rng.randint(-4, 4) / 2, rng.randint(-4, 4) / 2, rng.randint(-4, 4) / 2))
    cfg.append('Mem[0]=1.5, Mem[4]=2.0, Mem[8]=-1.0')
    return '\n'.join(cfg + [''] + prog) + '\n'


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 6385
    rng = random.Random(seed)
    failures = 0
    for i in range(count):
        text = random_config(rng, random_program(rng))
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as tf:
            tf.write(text)
            path = tf.name
        for w in (1, 2, 3, 4):
            errors, m = check(path, w)
            if errors:
                failures += 1
                print('program %d width %d FAILED:' % (i, w))
                print(text)
                for e in errors[:8]:
                    print('   ' + e)
                break
        os.unlink(path)
    print('%d random programs x 4 issue widths: %s'
          % (count, 'all passed' if not failures else '%d failed' % failures))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
