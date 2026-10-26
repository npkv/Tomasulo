# reference.py  (new, testing only)
# A plain sequential interpreter of the same ISA.  It knows nothing about
# pipelines; tests/check.py runs every test program on it and on the
# Tomasulo simulator (issue width 1..4) and requires identical final
# registers and memory, and the same committed instruction sequence.

from exe import alu


def run_reference(cfg, program, max_steps=100000):
    reg = {'R': [0] * 32, 'F': [0.0] * 32}
    for (kind, n), v in cfg.regs.items():
        reg[kind][n] = v
    memory = [0.0] * cfg.mem_bytes
    for a, v in cfg.mem.items():
        memory[a] = v

    def get(r):
        return 0 if r == ('R', 0) else reg[r[0]][r[1]]

    trace = []
    pc = 0
    steps = 0
    while 0 <= pc < len(program) and steps < max_steps:
        ins = program[pc]
        trace.append(pc)
        steps += 1
        op = ins.op
        nxt = pc + 1
        if op in ('Add', 'Sub', 'Add.d', 'Sub.d', 'Mult.d'):
            reg[ins.dest[0]][ins.dest[1]] = alu(op, get(ins.srcs[0]), get(ins.srcs[1]))
        elif op == 'Addi':
            reg[ins.dest[0]][ins.dest[1]] = alu(op, get(ins.srcs[0]), ins.imm)
        elif op == 'Ld':
            reg[ins.dest[0]][ins.dest[1]] = memory[int(get(ins.srcs[0])) + ins.imm]
        elif op == 'Sd':
            memory[int(get(ins.srcs[0])) + ins.imm] = get(ins.srcs[1])
        elif op in ('Beq', 'Bne'):
            a, b = get(ins.srcs[0]), get(ins.srcs[1])
            if (a == b) == (op == 'Beq'):
                nxt = pc + 1 + ins.imm
        reg['R'][0] = 0
        pc = nxt
    return reg, memory, trace, (0 <= pc < len(program))
