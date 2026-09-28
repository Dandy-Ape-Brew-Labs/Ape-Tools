#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"

out=$(python3 "$REPO_ROOT/tools/py-run/py_run.py" --system -c "print(2+2)")
assert_eq "$(echo "$out" | jqv 'd["stdout"].strip()')" "4"
assert_eq "$(echo "$out" | jqv 'd["exit"]')" "0"

echo 'import sys; print("args:", sys.argv[1:])' > s.py
out=$(python3 "$REPO_ROOT/tools/py-run/py_run.py" --system s.py a b)
assert_contains "args: ['a', 'b']" "$out"

echo "py-run OK"
