#!/bin/bash
# run_tests.sh - runs every test case with issue width 1, 2, 3 and 4, writes
# the simulator output to results/<test>_w<width>.txt and then runs the
# automatic checker (tests/check.py).
cd "$(dirname "$0")"
mkdir -p results
for t in tests/tc*.txt; do
	name=$(basename "$t" .txt)
	for w in 1 2 3 4; do
		python3 code/main.py "$t" --issue-width $w --show-squashed > results/${name}_w$w.txt
	done
done
# the handout's sample program never terminates (Bne R2, R3 is always taken)
for w in 1 2 3 4; do
	python3 code/main.py tests/spec_sample.txt --issue-width $w --max-cycles 40 > results/spec_sample_w$w.txt
done
python3 tests/check.py | tee results/check_summary.txt
