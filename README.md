# Tomasulo

Multi-issue (1–4 instructions per cycle, in-order issue) Tomasulo simulator with a ROB,
register renaming, speculative execution (8-entry BTB, 1-bit predictor) and memory
disambiguation. It extends the single-issue Python simulator in `original_code/`
(Qing, 2017).

Repository: https://github.com/npkv/Tomasulo
Companion assignment (branch predictor): https://github.com/npkv/Branch-Predictor

Report: `REPORT.pdf` (source `REPORT.md`). It covers what was added, test results under
issue widths 1–4, and verification.

## Run

```
python3 code/main.py tests/tc5_loop.txt                  # issue width from the file
python3 code/main.py tests/tc5_loop.txt --issue-width 4 --show-squashed
python3 code/main.py tests/spec_sample.txt --max-cycles 40   # handout sample (infinite loop)
```

Options: `--issue-width N` (1–4), `--cdb-width N`, `--commit-width N` (default = issue
width), `--show-squashed`, `--verbose` (cycle-by-cycle log), `--max-cycles N`,
`--no-config`.

Python 3.8+, standard library only.

## Tests

```
./run_tests.sh            # every test x widths 1-4 -> results/<test>_w<width>.txt, then the checker
python3 tests/check.py    # checks against a sequential reference + timing rules
python3 tests/fuzz.py 400 # random programs / configurations, widths 1-4
```

## Input format

```
                   # of rs   Cycles in EX   Cycles in Mem   # of FUs
Integer adder         2           1                            1
FP adder              3           3                            1
FP multiplier         2          20                            1
Load/store unit       3           1             4              1

ROB entries = 128
Issue width = 2
CDB width = 2           (optional, default = issue width)
Commit width = 2        (optional, default = issue width)
R1=10, R2=20, F2=30.1
Mem[4]=1, Mem[8]=2, Mem[12]=3.4

Add.d F1, F2, F3
Ld F4, 8(R1)
Bne R2, R3, -3
```

Instructions: `Ld`, `Sd`, `Beq`, `Bne`, `Add`, `Addi`, `Sub`, `Add.d`, `Sub.d`, `Mult.d`
(case insensitive, commas optional). Branch target = PC + 4 + (offset << 2).

## Layout

```
code/           simulator (main, config, init, issue, exe, mem, wb, commit, squash, branch, print_status, reference)
tests/          test programs tc1-tc9, spec_sample, check.py, fuzz.py
results/        simulator output for every test and width, check summary
original_code/  the starting single-issue simulator, unchanged, for reference
report/         chart and report source
REPORT.md/.pdf  report
```
