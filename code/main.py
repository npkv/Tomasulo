# main.py
# Multi-issue (1-4 wide, in-order issue) Tomasulo simulator with ROB,
# register renaming, speculative execution and memory disambiguation.
#
# Usage:
#   python3 main.py <input file> [--issue-width N] [--cdb-width N]
#                   [--commit-width N] [--show-squashed] [--verbose]
#                   [--max-cycles N] [--no-config]
#
# Original main.py (Qing, 2017) had the whole configuration (registers,
# memory, RS counts, latencies) hard-coded, read only the instruction list
# from code.in and ran one instruction per stage per cycle.  Now everything
# comes from the input file (see config.py), the issue width can also be given
# on the command line, and the result is printed in the required format.
#
# Order of the stages inside one simulated cycle.  Timing is decided by the
# cycle numbers stored in each entry (a value broadcast in cycle w is usable
# from w+1, an instruction issued in cycle i executes from i+1, ...), so the
# order below only decides which resources freed in a cycle can be reused in
# that same cycle:
#   COMMIT  frees ROB entries (and the LSQ entries of stores)  -> reusable by ISSUE
#   WB      broadcasts on the CDB
#   MEM     loads: forwarding / memory access
#   EX      starts operations, frees reservation stations      -> reusable by ISSUE
#   ISSUE   up to issue-width instructions
#   end of cycle: branches whose EX ends in this cycle are resolved

import argparse
import sys

from config import read_input, ConfigError
from init import Machine
from branch import BTB
from issue import issue
from exe import exe
from mem import mem
from wb import wb
from commit import commit, SimulationError
from squash import resolve_branches
from print_status import report


def simulate(cfg, program, max_cycles=100000):
    m = Machine(cfg, program)
    m.btb = BTB(cfg.btb_entries)
    cycle = 0
    truncated = False
    while True:
        cycle += 1
        m.cycle = cycle
        commit(m, cycle)
        wb(m, cycle)
        mem(m, cycle)
        exe(m, cycle)
        issue(m, cycle)
        resolve_branches(m, cycle)
        if not m.rob and not (0 <= m.pc < len(program)):
            break
        if cycle >= max_cycles:
            truncated = True
            break
    return m, truncated


def main(argv=None):
    ap = argparse.ArgumentParser(description='Multi-issue Tomasulo simulator')
    ap.add_argument('input')
    ap.add_argument('--issue-width', type=int, help='1..4, overrides the input file')
    ap.add_argument('--cdb-width', type=int, help='results broadcast per cycle (default = issue width)')
    ap.add_argument('--commit-width', type=int, help='instructions committed per cycle (default = issue width)')
    ap.add_argument('--show-squashed', action='store_true', help='also list wrong-path instructions')
    ap.add_argument('--verbose', action='store_true', help='print a cycle-by-cycle event log')
    ap.add_argument('--max-cycles', type=int, default=100000, help='stop after this many cycles')
    ap.add_argument('--no-config', action='store_true', help='do not echo the configuration')
    args = ap.parse_args(argv)

    try:
        cfg, program = read_input(args.input)
        if args.issue_width is not None:
            cfg.issue_width = args.issue_width
        if args.cdb_width is not None:
            cfg.cdb_width_req = args.cdb_width
        if args.commit_width is not None:
            cfg.commit_width_req = args.commit_width
        cfg.finish()
    except (ConfigError, OSError) as e:
        print('error: %s' % e, file=sys.stderr)
        return 2

    try:
        m, truncated = simulate(cfg, program, args.max_cycles)
    except SimulationError as e:
        print('simulation error: %s' % e, file=sys.stderr)
        return 3

    if args.verbose:
        for c, text in m.log:
            print('[%4d] %s' % (c, text))
        print()
    print(report(m, args.show_squashed, not args.no_config, truncated))
    return 0


if __name__ == '__main__':
    sys.exit(main())
