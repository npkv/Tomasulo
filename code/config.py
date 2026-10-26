# config.py  (new)
# Reads the simulator input file: hardware configuration, initial register
# and memory values, and the assembly program.  The text is case insensitive.
#
#                    # of rs   Cycles in EX   Cycles in Mem   # of FUs
#   Integer adder       2          1                             1
#   FP adder            3          3                             1
#   FP multiplier       2          20                            1
#   Load/store unit     3          1              4              1
#
#   ROB entries = 128
#   Issue width = 2             (1..4, default 1)
#   CDB width = 2               (optional, default = issue width)
#   Commit width = 2            (optional, default = issue width)
#   R1=10, R2=20, F2=30.1
#   Mem[4]=1, Mem[8]=2, Mem[12]=3.4
#
#   Add.d F1, F2, F3
#   Ld F4, 8(R1)
#   Bne R2, R3, -3
#
# Lines starting with '#' and text after '//' or ';' are comments.

import re

from init import Instruction


class ConfigError(Exception):
    pass


class Config:
    def __init__(self):
        # defaults = the sample configuration of the handout
        self.rs = {'int': 2, 'fpadd': 3, 'fpmul': 2, 'ldst': 3}
        self.ex = {'int': 1, 'fpadd': 3, 'fpmul': 20, 'ldst': 1}
        self.fus = {'int': 1, 'fpadd': 1, 'fpmul': 1, 'ldst': 1}
        self.mem_cycles = 4
        self.rob_size = 128
        self.issue_width = 1
        self.cdb_width_req = None   # from the file / command line; None -> issue width
        self.commit_width_req = None
        self.cdb_width = None
        self.commit_width = None
        self.mem_bytes = 256        # 256 B = 64 words
        self.btb_entries = 8
        self.regs = {}              # ('R', n) / ('F', n) -> initial value
        self.mem = {}               # byte address -> initial value

    def finish(self):
        if not 1 <= self.issue_width <= 4:
            raise ConfigError('issue width must be between 1 and 4 (got %d)' % self.issue_width)
        self.cdb_width = self.cdb_width_req or self.issue_width
        self.commit_width = self.commit_width_req or self.issue_width
        for name, d in (('# of rs', self.rs), ('cycles in EX', self.ex), ('# of FUs', self.fus)):
            for k, v in d.items():
                if v < 1:
                    raise ConfigError('%s of %s must be at least 1' % (name, k))
        if self.mem_cycles < 1 or self.rob_size < 1 or self.cdb_width < 1 or self.commit_width < 1:
            raise ConfigError('memory cycles, ROB entries, CDB and commit width must be >= 1')


UNIT_LINES = (
    ('integer adder', 'int'),
    ('fp adder', 'fpadd'),
    ('fp multiplier', 'fpmul'),
    ('load/store unit', 'ldst'),
)

OPCODES = {
    'add': 'Add', 'addi': 'Addi', 'sub': 'Sub',
    'add.d': 'Add.d', 'sub.d': 'Sub.d', 'mult.d': 'Mult.d', 'mul.d': 'Mult.d',
    'ld': 'Ld', 'sd': 'Sd', 'beq': 'Beq', 'bne': 'Bne',
}

REG_RE = re.compile(r'^([rf])(\d+)$', re.I)
MEMOP_RE = re.compile(r'^(-?\d+)\(([rf]\d+)\)$', re.I)


def parse_reg(tok, line_no, kinds='RF'):
    m = REG_RE.match(tok)
    if not m:
        raise ConfigError('line %d: "%s" is not a register' % (line_no, tok))
    kind, n = m.group(1).upper(), int(m.group(2))
    if kind not in kinds:
        raise ConfigError('line %d: register %s not allowed here' % (line_no, tok))
    if not 0 <= n < 32:
        raise ConfigError('line %d: register %s out of range (0..31)' % (line_no, tok))
    return (kind, n)


def parse_int(tok, line_no):
    try:
        return int(tok, 0)
    except ValueError:
        raise ConfigError('line %d: "%s" is not an integer' % (line_no, tok))


def parse_number(text, line_no):
    try:
        if re.match(r'^[+-]?\d+$', text):
            return int(text)
        return float(text)
    except ValueError:
        raise ConfigError('line %d: "%s" is not a number' % (line_no, text))


def reg_name(r):
    return '%s%d' % r


def parse_instruction(index, text, line_no):
    toks = [t for t in re.split(r'[\s,]+', text.strip()) if t]
    op = OPCODES.get(toks[0].lower())
    if op is None:
        raise ConfigError('line %d: unknown instruction "%s"' % (line_no, toks[0]))
    args = toks[1:]

    def need(n):
        if len(args) != n:
            raise ConfigError('line %d: %s needs %d operands' % (line_no, op, n))

    if op in ('Add', 'Sub'):
        need(3)
        d, s, t = (parse_reg(a, line_no, 'R') for a in args)
        ins = Instruction(index, None, op, d, [s, t], None, line_no)
        shown = '%s %s, %s, %s' % (op, reg_name(d), reg_name(s), reg_name(t))
    elif op == 'Addi':
        need(3)
        d = parse_reg(args[0], line_no, 'R')
        s = parse_reg(args[1], line_no, 'R')
        imm = parse_int(args[2], line_no)
        ins = Instruction(index, None, op, d, [s], imm, line_no)
        shown = '%s %s, %s, %d' % (op, reg_name(d), reg_name(s), imm)
    elif op in ('Add.d', 'Sub.d', 'Mult.d'):
        need(3)
        d, s, t = (parse_reg(a, line_no, 'F') for a in args)
        ins = Instruction(index, None, op, d, [s, t], None, line_no)
        shown = '%s %s, %s, %s' % (op, reg_name(d), reg_name(s), reg_name(t))
    elif op in ('Ld', 'Sd'):
        if len(args) == 3:                      # "Ld F1 0 (R1)" style spacing
            args = [args[0], args[1] + args[2]]
        need(2)
        a = parse_reg(args[0], line_no)
        m = MEMOP_RE.match(args[1].replace(' ', ''))
        if not m:
            raise ConfigError('line %d: memory operand must look like offset(Rn)' % line_no)
        off = int(m.group(1))
        base = parse_reg(m.group(2), line_no, 'R')
        if op == 'Ld':
            ins = Instruction(index, None, op, a, [base], off, line_no)
        else:
            ins = Instruction(index, None, op, None, [base, a], off, line_no)
        shown = '%s %s, %d(%s)' % (op, reg_name(a), off, reg_name(base))
    else:                                       # Beq / Bne
        need(3)
        s = parse_reg(args[0], line_no, 'R')
        t = parse_reg(args[1], line_no, 'R')
        off = parse_int(args[2], line_no)
        ins = Instruction(index, None, op, None, [s, t], off, line_no)
        shown = '%s %s, %s, %d' % (op, reg_name(s), reg_name(t), off)
    ins.text = shown
    return ins


def read_input(path):
    cfg = Config()
    program = []
    with open(path) as f:
        lines = f.read().splitlines()
    for line_no, raw in enumerate(lines, 1):
        line = raw.split('//')[0].split(';')[0].strip()
        if not line or line.startswith('#'):
            continue
        low = line.lower()

        # functional unit lines
        unit = next((key for name, key in UNIT_LINES if low.startswith(name)), None)
        if unit is not None:
            nums = [int(x) for x in re.findall(r'\d+', low[len(next(n for n, k in UNIT_LINES if k == unit)):])]
            if unit == 'ldst':
                if len(nums) != 4:
                    raise ConfigError('line %d: Load/store unit needs: # of rs, EX cycles, MEM cycles, # of FUs' % line_no)
                cfg.rs['ldst'], cfg.ex['ldst'], cfg.mem_cycles, cfg.fus['ldst'] = nums
            else:
                if len(nums) != 3:
                    raise ConfigError('line %d: expected: # of rs, EX cycles, # of FUs' % line_no)
                cfg.rs[unit], cfg.ex[unit], cfg.fus[unit] = nums
            continue

        m = re.match(r'^(rob entries|issue width|cdb width|commit width|btb entries)\s*[=:]\s*(\d+)$', low)
        if m:
            v = int(m.group(2))
            attr = {'rob entries': 'rob_size', 'issue width': 'issue_width',
                    'cdb width': 'cdb_width_req', 'commit width': 'commit_width_req',
                    'btb entries': 'btb_entries'}[m.group(1)]
            setattr(cfg, attr, v)
            continue

        if re.match(r'^mem\s*\[', low):
            for am, vm in re.findall(r'mem\s*\[\s*(\d+)\s*\]\s*=\s*([-+0-9.eE]+)', line, re.I):
                addr = int(am)
                if not 0 <= addr < cfg.mem_bytes:
                    raise ConfigError('line %d: Mem[%d] is outside the %d-byte memory'
                                      % (line_no, addr, cfg.mem_bytes))
                cfg.mem[addr] = float(parse_number(vm, line_no))
            continue

        if re.match(r'^[rf]\d+\s*=', low):
            for rm, vm in re.findall(r'([rf]\d+)\s*=\s*([-+0-9.eE]+)', line, re.I):
                r = parse_reg(rm, line_no)
                v = parse_number(vm, line_no)
                if r[0] == 'R':
                    if r[1] == 0:
                        continue                        # R0 is hard-wired to 0
                    cfg.regs[r] = int(v)
                else:
                    cfg.regs[r] = float(v)
            continue

        program.append(parse_instruction(len(program), line, line_no))

    cfg.finish()
    if not program:
        raise ConfigError('no instructions found in ' + path)
    return cfg, program
