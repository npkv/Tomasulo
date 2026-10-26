# init.py
# Data structures of the Tomasulo machine.
#
# Based on init.py of the original single-issue simulator (Qing, 2017).  The
# original built every record from a fresh namedtuple *class* and then stored
# fields as class attributes; that is replaced by ordinary classes with
# __slots__.  New: Machine (all state in one place), branch fields in the ROB
# entry, operand records that remember the cycle a value became available,
# and functional-unit pools with pipelined / unpipelined timing.

from collections import deque


class Operand:
    """A source operand of an RS / LSQ entry.

    Either 'tag' is set (waiting for that ROB entry to broadcast) or 'value'
    is valid since cycle 'avail'.  An instruction may start executing in
    cycle c only when every operand has avail < c (a value broadcast on the
    CDB in cycle w can be used for execution from cycle w+1 on).
    """
    __slots__ = ('tag', 'value', 'avail')

    def __init__(self, tag=None, value=None, avail=0):
        self.tag = tag
        self.value = value
        self.avail = avail

    def ready(self, cycle):
        return self.tag is None and self.avail < cycle

    def __repr__(self):
        return 'wait(%s)' % self.tag.name if self.tag is not None else repr(self.value)


class Instruction:
    """One static instruction of the program."""
    __slots__ = ('index', 'text', 'op', 'dest', 'srcs', 'imm', 'line')

    def __init__(self, index, text, op, dest, srcs, imm, line):
        self.index = index      # word address of the instruction (PC / 4)
        self.text = text        # normalised assembly text, used in the output
        self.op = op            # canonical opcode: Add, Addi, Sub, Add.d, Sub.d,
                                # Mult.d, Ld, Sd, Beq, Bne
        self.dest = dest        # destination register ('R', n) / ('F', n) or None
        self.srcs = srcs        # list of source registers
        self.imm = imm          # immediate / offset (int) or None
        self.line = line        # line number in the input file


class ROBEntry:
    __slots__ = ('seq', 'slot', 'ins', 'dest', 'value', 'issue', 'ex', 'mem', 'wb',
                 'commit', 'pred_taken', 'pred_target', 'taken', 'target',
                 'mispredicted', 'squashed', 'fault', 'forwarded')

    def __init__(self, seq, slot, ins, cycle):
        self.seq = seq          # dynamic sequence number (program order)
        self.slot = slot        # ROB slot number, shown as ROB<slot>
        self.ins = ins
        self.dest = ins.dest
        self.value = None
        self.issue = cycle
        self.ex = None          # (first, last) EX cycle
        self.mem = None         # (first, last) MEM cycle
        self.wb = None          # CDB cycle
        self.commit = None
        self.pred_taken = False # branch prediction made at ISSUE
        self.pred_target = None
        self.taken = None       # branch outcome, known at the end of EX
        self.target = None
        self.mispredicted = False
        self.squashed = False
        self.fault = None       # bad memory address (only an error if it commits)
        self.forwarded = False  # load got its value from an older store

    @property
    def name(self):
        return 'ROB%d' % self.slot


class RSEntry:
    """Reservation station entry (integer adder, FP adder, FP multiplier)."""
    __slots__ = ('busy', 'op', 'src1', 'src2', 'rob')

    def __init__(self):
        self.busy = False
        self.op = None
        self.src1 = None        # Operand
        self.src2 = None        # Operand
        self.rob = None         # destination ROB entry

    def ready(self, cycle):
        return (self.busy and self.src1.ready(cycle) and self.src2.ready(cycle)
                and self.rob.issue < cycle)


class LSQEntry:
    """Load/store queue entry, kept in program order."""
    __slots__ = ('rob', 'op', 'base', 'imm', 'data', 'address', 'addr_cycle',
                 'addr_started', 'mem_started', 'done_cycle')

    def __init__(self, rob, op, base, imm, data):
        self.rob = rob
        self.op = op            # 'Ld' or 'Sd'
        self.base = base        # Operand: base register
        self.imm = imm
        self.data = data        # Operand: store data (None for loads)
        self.address = None
        self.addr_cycle = None  # last cycle of the address calculation
        self.addr_started = False
        self.mem_started = False
        self.done_cycle = None  # load: cycle its value was obtained -> entry freed after it


class FUPool:
    """All functional units of one kind.

    pipelined   : every unit can start a new operation each cycle
    unpipelined : a unit is busy for 'latency' cycles per operation
    """

    def __init__(self, name, count, latency, pipelined):
        self.name = name
        self.count = count
        self.latency = latency
        self.pipelined = pipelined
        self.busy_until = [0] * count   # unpipelined: last busy cycle of each unit
        self.started = {}               # pipelined: cycle -> operations started

    def can_start(self, cycle):
        if self.pipelined:
            return self.started.get(cycle, 0) < self.count
        return any(b < cycle for b in self.busy_until)

    def start(self, cycle):
        """Reserve a unit; returns the unit number (for squash bookkeeping)."""
        if self.pipelined:
            self.started[cycle] = self.started.get(cycle, 0) + 1
            return None
        for u, b in enumerate(self.busy_until):
            if b < cycle:
                self.busy_until[u] = cycle + self.latency - 1
                return u
        raise RuntimeError('no free unit in ' + self.name)

    def release(self, unit, cycle):
        """A squashed instruction gives its unpipelined unit back."""
        if unit is not None and not self.pipelined:
            self.busy_until[unit] = min(self.busy_until[unit], cycle)


class InFlight:
    """An ALU operation / branch inside a functional unit."""
    __slots__ = ('rob', 'pool', 'unit', 'value', 'last_cycle')

    def __init__(self, rob, pool, unit, value, last_cycle):
        self.rob = rob
        self.pool = pool
        self.unit = unit
        self.value = value
        self.last_cycle = last_cycle


class PendingResult:
    """A finished result waiting for a CDB slot."""
    __slots__ = ('rob', 'value', 'ready_cycle')

    def __init__(self, rob, value, ready_cycle):
        self.rob = rob
        self.value = value
        self.ready_cycle = ready_cycle  # first cycle it may be broadcast


class Machine:
    """Complete processor state."""

    def __init__(self, cfg, program):
        self.cfg = cfg
        self.program = program
        # architectural state
        self.reg = {'R': [0] * 32, 'F': [0.0] * 32}
        for (kind, n), v in cfg.regs.items():
            self.reg[kind][n] = v
        self.reg['R'][0] = 0
        # as in the original code: 256 byte addresses, each slot holds one
        # value (programs normally use word-aligned addresses 0, 4, 8, ...)
        self.memory = [0.0] * cfg.mem_bytes
        for addr, v in cfg.mem.items():
            self.memory[addr] = v
        # register alias table: register -> ROB entry (None = value in register file)
        self.rat = {'R': [None] * 32, 'F': [None] * 32}
        # reservation stations
        self.rs = {
            'int': [RSEntry() for _ in range(cfg.rs['int'])],
            'fpadd': [RSEntry() for _ in range(cfg.rs['fpadd'])],
            'fpmul': [RSEntry() for _ in range(cfg.rs['fpmul'])],
        }
        # functional units: integer adder unpipelined, FP units pipelined,
        # load/store address adder pipelined, memory single-ported unpipelined
        self.fu = {
            'int': FUPool('Integer adder', cfg.fus['int'], cfg.ex['int'], False),
            'fpadd': FUPool('FP adder', cfg.fus['fpadd'], cfg.ex['fpadd'], True),
            'fpmul': FUPool('FP multiplier', cfg.fus['fpmul'], cfg.ex['fpmul'], True),
            'addr': FUPool('Address adder', cfg.fus['ldst'], cfg.ex['ldst'], True),
        }
        self.mem_busy_until = 0         # last cycle the memory port is busy
        self.mem_user = None            # ROB entry of the load using the port
        self.lsq = []                   # LSQEntry list in program order
        self.writing = []               # committed stores still writing memory
                                        # (LSQEntry, last write cycle); loads may
                                        # still forward from them
        self.rob = deque()              # ROBEntry in program order
        self.next_seq = 0
        self.next_slot = 0
        self.in_flight = []             # InFlight
        self.results = []               # PendingResult waiting for the CDB
        self.resolutions = []           # branches resolving at the end of a cycle
        # front end
        self.pc = 0                     # word address of the next instruction to fetch
        self.fetch_resume = 1           # first cycle fetch may continue (misprediction)
        # bookkeeping
        self.finished = []              # committed ROB entries in commit order
        self.squashed = []              # squashed ROB entries
        self.stats = {'branches': 0, 'mispredictions': 0}
        self.log = []                   # (cycle, text) events for --verbose
        self.cycle = 0

    def note(self, cycle, text):
        self.log.append((cycle, text))
