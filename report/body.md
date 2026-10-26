# Programming Assignment: Tomasulo Algorithm with Multiple Issue

**Adding 1–4-wide in-order issue to a Tomasulo simulator with ROB, register renaming, speculative execution and memory disambiguation**

| Item | Details |
|---|---|
| Student | Nagendra |
| GitHub repository (this assignment) | <https://github.com/npkv/Tomasulo> |
| GitHub repository (branch predictor assignment) | <https://github.com/npkv/Branch-Predictor> |

## 1. Introduction

I started from the existing Python Tomasulo simulator, `original_code/` (Qing, 2017;
github.com/qingyangqing/Tomasulo), which supports a single issue per cycle. The work
covered four things:

1. **Multiple issue (1–4 instructions per cycle, in order).** The width comes from the
   input file (`Issue width = N`) or from `--issue-width N`. Write-back (CDB) and commit
   are as wide as issue by default. Each can be set separately, for example
   `CDB width = 1` for a single CDB.
2. **The rest of the specified machine**, which the starting code did not have: input-file
   configuration (number of RS, EX cycles, MEM cycles, number of FUs, ROB size, registers,
   memory), the 8-entry BTB with a 1-bit predictor, speculative execution with misprediction
   recovery, `Beq`, an unpipelined integer adder, and the required output (instruction
   status table, register values, non-zero memory).
3. **Bug fixes in the starting code.** Several bugs became visible, or got worse, once more
   than one instruction is in flight per cycle (Section 2).
4. **Test cases and automatic verification.** Nine test programs run under issue widths
   1–4. Every run is checked against a sequential reference interpreter and against a set
   of timing rules, and a random-program stress test is included (Section 7).

### What works

* Issue width 1, 2, 3 and 4 (in-order issue; issue stops at the first structural hazard).
* Out-of-order execution with register renaming through the RAT/ROB, and in-order commit.
* Multiple functional units of each kind. The integer adder is unpipelined; the FP adder and
  FP multiplier are pipelined.
* Load/store queue with a dedicated address adder, store-to-load forwarding (1 cycle),
  conservative memory disambiguation, stores writing memory at commit, and a single-ported
  non-pipelined memory.
* Branch prediction with the 8-entry BTB and 1-bit predictor, prediction at ISSUE,
  resolution at the end of EX, squash plus RAT recovery, and correct fetch at n+2.
* All 36 test runs (9 tests × 4 widths) and 1,600 random runs produce the same registers,
  memory and committed instruction stream as the sequential reference.

### Limitations / known differences

* Memory disambiguation is conservative: a load waits until every older store's address is
  known; it never speculates past unknown store addresses.
* As in the original code, memory is an array of 256 byte addresses with one value per
  address, and there is no byte-level overlap between neighbouring words. Programs normally
  use word-aligned addresses; the handout's own sample loads from address 18, which this
  model accepts.
* Values are kept as Python floats (double precision) rather than rounded to single
  precision.
* By default the CDB and commit widths equal the issue width (as in the sample report).
  Set `CDB width = 1` / `Commit width = 1` for a single CDB; Section 6.4 shows the effect.

## 2. Problems found in the starting code

| # | Original behaviour | Effect | Fix |
|---|---|---|---|
| 1 | `mem.py`: `if (check_if_sd_committable):` names the function but never calls it (always true), and the function reads a non-existent field `ldsd_tag` | stores could write memory **before** they commit, so a squashed store would corrupt memory | stores write memory only in COMMIT (`commit.py`) |
| 2 | `wb.py`: a broadcast writes the value into the RAT for the destination register unconditionally | if a younger instruction has already renamed the same register, the RAT loses that mapping and later readers get a stale value (a WAW bug that happens much more often with multiple issue) | the RAT maps registers to ROB entries only; values are read from the ROB, and commit clears a RAT entry only if it still points at the committing entry |
| 3 | `mem.py`: the load "has no data yet" test examines `ld_sd_queue[0]` instead of the load being scheduled; forwarding only looks at the nearest older store | wrong loads selected, missed forwarding | per-load checks; youngest older matching store |
| 4 | `issue.py`: after a `Bne` fetch stops until it resolves; no prediction; no `Beq`; branch offset in bytes | no speculation | BTB + 1-bit predictor, speculative issue, squash/recovery, `Beq`, word offsets as in the ISA (`PC+4+offset<<2`) |
| 5 | `main.py`: every parameter hard-coded; the input file holds only instructions | cannot run the required inputs | full input-file parser (`config.py`) |
| 6 | `exe.py`: the integer adder is pipelined, one unit per kind, and the FU entry can be advanced twice in one cycle (the sample report needed a workaround) | wrong timing | explicit start/end cycles per operation; pipelined and unpipelined unit pools with "# of FUs" units |
| 7 | records are built from a new `namedtuple` *class* per entry, with fields stored as class attributes | fragile shared state | plain classes with `__slots__` (`init.py`) |
| 8 | registers and memory are never printed | output incomplete | `print_status.py` prints the required output |

## 3. Code changes

The module structure of the original is kept. Every original file has a header comment
describing what it did and what was changed. New files are marked "(new)".

| File | Role | Changes |
|---|---|---|
| `main.py` | cycle loop, command line | Reads the input file. Options: `--issue-width`, `--cdb-width`, `--commit-width`, `--show-squashed`, `--verbose`, `--max-cycles`. Stage order per cycle: COMMIT → WB → MEM → EX → ISSUE → branch resolution. |
| `config.py` (new) | input parser | Case-insensitive; FU table, `ROB entries`, `Issue width`, optional `CDB width` / `Commit width`, register and memory initial values, instructions with or without commas. |
| `init.py` | data structures | `Machine`, `ROBEntry` (with branch fields), `RSEntry`, `LSQEntry`, `Operand` (value + cycle it became available), `FUPool` (pipelined / unpipelined, N units). |
| `issue.py` | ISSUE | **Multi-issue loop** (below), renaming inside the issue group, BTB prediction, group ends after a predicted-taken branch, fetch stall after a misprediction. |
| `exe.py` | EX | Oldest-first selection; up to "# of FUs" starts per cycle; unpipelined integer adder; branch outcome computed; address calculation on the address adder. |
| `mem.py` | MEM (loads) | Disambiguation, forwarding from queued stores and from committed stores still writing memory, single memory port. |
| `wb.py` | WB / CDB | Up to `cdb_width` broadcasts per cycle, oldest first; no RAT write (bug 2). |
| `commit.py` | COMMIT | Up to `commit_width` in order; stores write memory here; RAT entry cleared only if still mapped to the entry. |
| `branch.py` (new) | BTB | 8 entries, index = word address mod 8, tag = full word address, target, 1-bit prediction. |
| `squash.py` (new) | recovery | Updates the BTB; on a misprediction removes younger ROB/RS/LSQ/FU/CDB entries, rebuilds the RAT, redirects fetch to cycle n+2. |
| `print_status.py` | output | Instruction status table, register values, non-zero memory, summary; optionally the squashed instructions. |
| `reference.py` (new) | testing | Sequential ISA interpreter used by the checker. |

The core multi-issue change in `issue.py`:

```python
# Original: exactly one instruction per call
def issue(cycle, PC, instructions, ROB, size_ROB, rs_int_adder, ...):
    ins = instructions[PC.PC]
    ...

# Now: up to issue_width instructions per cycle, strictly in order
def issue(m, cycle):
    if cycle < m.fetch_resume:                  # misprediction: fetch restarts at n+2
        return
    issued = 0
    while issued < m.cfg.issue_width and 0 <= m.pc < len(m.program):
        ins = m.program[m.pc]
        rob = issue_one(m, ins, cycle)          # ROB + RS/LSQ + renaming
        if rob is None:                         # ROB / RS / LSQ full: stop, stay in order
            break
        issued += 1
        if ins.op in ('Beq', 'Bne'):
            taken, target = m.btb.predict(m.pc) # 1-bit predictor + BTB at ISSUE
            rob.pred_taken, rob.pred_target = taken, target
            m.pc = target
            if taken:                           # redirect: rest of the group is dropped
                break
        else:
            m.pc += 1
```

Because each instruction in a group reads the RAT after the earlier ones have renamed their
destinations, dependences *inside* a group are renamed correctly. For example, in
`Add.d F3,…` followed by `Mult.d F4, F3, F3` in the same cycle, the multiply waits on the
add's ROB tag.

`wb.py` and `commit.py` have the same shape: a loop of up to `cdb_width` (or `commit_width`)
iterations over the oldest eligible entries.

## 4. Timing model

| Rule | Value |
|---|---|
| ISSUE | up to *W* per cycle, in order; stops at the first instruction without a ROB entry, RS or LSQ slot |
| EX start | ≥ issue + 1, and ≥ (cycle the last operand was broadcast) + 1 |
| EX length | "Cycles in EX"; integer adder busy for the whole time (unpipelined); FP units and the address adder accept one new op per unit per cycle |
| RS release | when EX starts (usable by an ISSUE in the same cycle) |
| MEM (load) | ≥ address EX end + 1; waits for older unknown store addresses; forwarding takes 1 cycle; memory access takes "Cycles in Mem" on the single port |
| WB | ≥ end of EX (or MEM for loads) + 1; up to the CDB width per cycle, oldest first |
| COMMIT | ≥ WB + 1 (branches: ≥ EX end + 1); in order; up to the commit width |
| Store | commits when address and data are known and the memory port is free; writes memory during commit for "Cycles in Mem" cycles (MEM column) |
| Branch | predicted at ISSUE; resolved at the end of its last EX cycle *n*; recovery in *n*+1; correct fetch in *n*+2 |
| Predicted-taken branch | ends the issue group; fetch continues at the target in the next cycle |

## 5. Input and output

Input is the format from the handout. Case is ignored, commas are optional, and lines
starting with `#` are comments. `CDB width` and `Commit width` are optional additions.

```
                   # of rs   Cycles in EX   Cycles in Mem   # of FUs
Integer adder         2           1                            1
FP adder              3           3                            1
FP multiplier         2          20                            1
Load/store unit       3           1             4              1

ROB entries = 128
Issue width = 2
R1=10, R2=20, F2=30.1
Mem[4]=1, Mem[8]=2, Mem[12]=3.4

Add.d F1, F2, F3
Ld F4, 8(R1)
Bne R2, R3, -3
```

The output is the instruction status table, one row per committed dynamic instruction with
the cycle of every stage, followed by `REGISTER VALUES` (R0–R31, F0–F31) and
`NON-ZERO MEMORY VALUES`. EX/MEM ranges are printed as `first-last`. Stores show their
memory write in the MEM column; stores and branches have no WB. With `--show-squashed`, the
wrong-path instructions are listed separately.

```
python3 code/main.py tests/tc5_loop.txt --issue-width 2 --show-squashed
./run_tests.sh        # all tests x widths 1-4 -> results/, then tests/check.py
```

## 6. Test cases and results under different issue widths

| Test | What it exercises |
|---|---|
| tc1_independent | 12 independent instructions with enough units: throughput should grow with width |
| tc2_renaming | RAW, WAR and WAW on F3 and R1 (also inside one issue group); writes to R0 |
| tc3_structural | ROB of 4 entries, 1 RS per unit, 1 LSQ entry: issue stalls stay in order |
| tc4_memory | store→load forwarding with late store data; load bypassing a non-matching store; load waiting for an unknown store address |
| tc5_loop | the original simulator's loop (3 iterations): loop-carried values, BTB prediction, mispredictions at the first iteration and at the exit |
| tc6_mispredict | two taken branches that miss in the BTB; wrong-path ALU ops and a wrong-path **store** must be squashed |
| tc7_btb_alias | two branches mapping to the same BTB entry (word 1 and word 9) keep evicting each other |
| tc8 / tc9 | test cases #01 and #02 of the sample report (same configuration and program) |
| spec_sample | the handout's sample input (never terminates: R3 is never written, so `Bne R2, R3` is always taken); run for 40 cycles |

### 6.1 Summary (default: CDB width = commit width = issue width)

{{SUMMARY_TABLE}}

![Total cycles of every test under issue widths 1–4](report/cycles_by_width.png)

**Discussion.**

* **tc1 (independent work)** shows the clearest effect of the wider front end: 18 → 12 →
  10 → 9 cycles (IPC 0.67 → 1.33). The gain beyond width 2 shrinks because only two integer
  adders, two FP adders, two multipliers and one memory port exist. In-order commit also
  waits for the 4-cycle multiplies.
* **True dependences limit the others.** tc2 is a dependence chain through a 6-cycle
  multiply, so widths 2–4 all finish in 21 cycles. tc5 and tc8/tc9 are dominated by the
  15/20-cycle multiplies and the single non-pipelined memory port, so wider issue only
  fills the window sooner (tc5: 57 → 51; tc8: 36 → 33).
* **Structural hazards (tc3).** With a 4-entry ROB and 1 RS per unit, issue stalls at the
  first full resource and stays in order. Width 4 gains only 4 cycles over width 1.
* **Speculation (tc6, tc7).** Results are correct at every width. Wider issue puts **more
  wrong-path instructions** into the machine before a branch resolves (tc6: 3, 5, 7, 9
  squashed for widths 1–4; tc7: 5, 14, 20, 20), and all of them are discarded. In tc7 the
  aliasing branches are mispredicted every time, so the n+2 refetch penalty dominates and
  width barely matters.

### 6.2 Example: tc1 with width 1 and width 4

{{TC1_TABLES}}

At width 4, the first four instructions issue together in cycle 1 and start executing in
cycle 2 on different units. Four instructions also commit together (cycle 7, after the
multiply's WB in cycle 6).

### 6.3 Example: misprediction recovery (tc6, width 2)

{{TC6_TABLE}}

`Beq R1, R2, 3` misses in the BTB, so it is predicted not taken and the wrong-path
`Addi R3`, `Sd F1` and `Add.d F1` are issued in cycles 1–2. The branch resolves (taken) at
the end of its EX in cycle 2; recovery happens in cycle 3, and the correct instruction
`Ld F2` is issued in cycle **4** = n+2. The same happens for `Bne` (resolved in cycle 8,
refetch in cycle 10). The wrong-path store never reaches memory: Mem[0] keeps 7.0, and R3 =
5, F1 = 2.0, F3 = 9.0 are the architecturally correct values.

### 6.4 Effect of a single CDB

With `--cdb-width 1 --commit-width 1` (one CDB, one commit per cycle), tc1 needs 18 / 17 / 16
/ 16 cycles for widths 1–4, against 18 / 12 / 10 / 9 with matching widths. A single CDB
serialises write-back: in the width-4 run, results finish EX in cycles 2–5 but are broadcast
one per cycle in cycles 3–14. A wider issue stage therefore needs a matching number of
result buses and commit ports to pay off. tc5 gives 57 / 55 / 55 / 55, and tc8 stays at 36
at every width.

### 6.5 Comparison with the sample report

tc8 and tc9 use the sample report's configurations and programs. Total cycles equal the
sample report's for widths 1 and 2 (tc8: 36 and 33; tc9: 47 and 46).

* **tc8, width 2:** the instruction status table is identical to the sample report's
  Figure 2, row for row.
* **tc8, width 1:** one difference. When two results are ready in the same cycle, this
  simulator broadcasts the older instruction first (`Mult.d F2, F1, F1` in cycle 16, then
  the second `Ld F1` in cycle 17). The sample report used completion order, so it has the
  reverse.
* **tc9:** a few rows differ. In the sample, the second load's memory access (7–11)
  overlaps the first load's (3–7) on the single memory port, and `Addi R1, R1, 8` starts EX
  in cycle 9, the same cycle its operand is broadcast. This simulator serialises the memory
  port (second load at 8–12) and starts dependants in the cycle after the broadcast (EX in
  cycle 10). The end-to-end time is the same either way, because the multiplies dominate.

The sample report's version could not run branches at widths above 1; this simulator runs
them at every width (tc5–tc7).

## 7. Verification

**`tests/check.py`** runs every test at widths 1–4 and checks:

* **Functional:** the committed instruction sequence, final registers and final memory are
  identical to a plain sequential interpreter of the same ISA (`code/reference.py`).
* **Timing / structural:** issue in order and ≤ *W* per cycle (wrong-path instructions
  included); commit in order and ≤ commit width; EX after ISSUE with exactly the
  configured length; WB after EX/MEM; COMMIT after WB; no instruction starts EX before
  each producer's WB (RAW); ≤ CDB width broadcasts per cycle; the memory port is never used
  twice in one cycle; the unpipelined integer adder count is never exceeded and pipelined
  units start ≤ "# of FUs" ops per cycle; after a misprediction resolved in cycle *n*, the
  next instruction issues no earlier than *n*+2; forwarded loads always have an older store
  to the same address in flight.

**`tests/fuzz.py`** generates random programs (all ALU ops, loads and stores to overlapping
addresses, forward branches, a counted loop) on random configurations (ROB 2–32 entries,
1–5 RS, 1–2 units, random latencies) and applies the same checks at all four widths. With
400 programs × 4 widths, about 22,000 committed instructions, 1,700 mispredictions,
4,000 squashed instructions and 280 forwarded loads, every check passed.

```
$ python3 tests/check.py      ->  ALL CHECKS PASSED   (36 runs)
$ python3 tests/fuzz.py 400   ->  400 random programs x 4 issue widths: all passed
```

During development the checks found a real issue. A store that committed in the same cycle
a load wanted to forward from it had already left the queue, so the load waited for the
store's memory write instead. In tc4 this made width 4 slower than width 1 (28 vs 20
cycles). Committed stores now stay visible for forwarding until their write completes (a
small write buffer), and tc4 takes 18 cycles at width 4.

## 8. How to run

```
python3 code/main.py <input file> [--issue-width N] [--cdb-width N] [--commit-width N]
                                  [--show-squashed] [--verbose] [--max-cycles N]
./run_tests.sh                    # all tests, widths 1-4, outputs in results/
python3 tests/check.py            # verification
python3 tests/fuzz.py 400         # random stress test
```

Python 3.8 or newer, standard library only. `--verbose` prints a cycle-by-cycle event log
(issue, EX start, MEM, WB, commit, prediction, squash).

## Appendix: instruction status tables for every test and issue width

Full outputs, including all register values, are in `results/<test>_w<width>.txt`.
Configuration lines are omitted here; registers and memory list non-zero values only.

{{APPENDIX}}
