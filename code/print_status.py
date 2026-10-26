# print_status.py
# Output in the format required by the assignment: the instruction status
# table (cycle of every stage), register values and non-zero memory values.
#
# Original (Qing, 2017): printed the namedtuple fields of RS / ROB entries for
# debugging and printed each instruction when it committed; registers and
# memory were never printed.


def fmt_range(r):
    if r is None:
        return ''
    a, b = r
    return '%d' % a if a == b else '%d-%d' % (a, b)


def fmt_value(v):
    if isinstance(v, float):
        s = '%.6g' % v
        if '.' not in s and 'e' not in s and 'inf' not in s and 'nan' not in s:
            s += '.0'
        return s
    return str(v)


def config_lines(m):
    c = m.cfg
    out = []
    out.append('%-18s%10s%14s%15s%10s' % ('', '# of rs', 'Cycles in EX', 'Cycles in Mem', '# of FUs'))
    out.append('%-18s%10d%14d%15s%10d' % ('Integer adder', c.rs['int'], c.ex['int'], '', c.fus['int']))
    out.append('%-18s%10d%14d%15s%10d' % ('FP adder', c.rs['fpadd'], c.ex['fpadd'], '', c.fus['fpadd']))
    out.append('%-18s%10d%14d%15s%10d' % ('FP multiplier', c.rs['fpmul'], c.ex['fpmul'], '', c.fus['fpmul']))
    out.append('%-18s%10d%14d%15d%10d' % ('Load/store unit', c.rs['ldst'], c.ex['ldst'], c.mem_cycles, c.fus['ldst']))
    out.append('ROB entries = %d, Issue width = %d, CDB width = %d, Commit width = %d, BTB entries = %d'
               % (c.rob_size, c.issue_width, c.cdb_width, c.commit_width, c.btb_entries))
    return out


def status_table(entries, width=26):
    out = ['%-*s%-8s%-10s%-10s%-6s%-8s' % (width, '', 'ISSUE', 'EX', 'MEM', 'WB', 'COMMIT')]
    for e in entries:
        out.append('%-*s%-8s%-10s%-10s%-6s%-8s' % (
            width, e.ins.text, e.issue, fmt_range(e.ex), fmt_range(e.mem),
            '' if e.wb is None else e.wb, '' if e.commit is None else e.commit))
    return out


def register_lines(m):
    out = ['REGISTER VALUES', '']
    for kind in ('R', 'F'):
        for start in range(0, 32, 8):
            names = ''.join('%-10s' % ('%s%d' % (kind, i)) for i in range(start, start + 8))
            vals = ''.join('%-10s' % fmt_value(m.reg[kind][i]) for i in range(start, start + 8))
            out.append('        ' + names.rstrip())
            out.append('value:  ' + vals.rstrip())
        out.append('')
    return out


def memory_lines(m):
    out = ['NON-ZERO MEMORY VALUES', '', '%-14s%s' % ('Addresses', 'Values')]
    nz = [(a, v) for a, v in enumerate(m.memory) if v != 0]
    for addr, v in nz:
        out.append('%-14s%s' % (addr, fmt_value(v)))
    if not nz:
        out.append('(none)')
    return out


def report(m, show_squashed=False, show_config=True, truncated=False):
    out = []
    if show_config:
        out += config_lines(m) + ['']
    width = max(26, max((len(e.ins.text) for e in m.finished + m.squashed), default=0) + 2)
    out += status_table(m.finished, width)
    if truncated:
        out.append('... stopped after %d cycles (--max-cycles); %d instructions still in flight'
                   % (m.cycle, len(m.rob)))
    out.append('')
    if show_squashed and m.squashed:
        out.append('SQUASHED (wrong-path) INSTRUCTIONS')
        out += status_table(sorted(m.squashed, key=lambda e: e.seq), width)
        out.append('')
    out += register_lines(m)
    out += memory_lines(m)
    out.append('')
    n = len(m.finished)
    last = m.finished[-1].commit if m.finished else 0
    out.append('SUMMARY: %d instructions committed in %d cycles (IPC = %.3f); '
               'branches = %d, mispredicted = %d; squashed instructions = %d'
               % (n, last, (n / last) if last else 0.0, m.stats['branches'],
                  m.stats['mispredictions'], len(m.squashed)))
    return '\n'.join(out)
