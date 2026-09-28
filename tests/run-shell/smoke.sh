#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"

out=$(python3 "$REPO_ROOT/tools/run-shell/run_shell.py" "echo hello; exit 3")
assert_eq "$(echo "$out" | jqv 'd["exit"]')" "3"
assert_eq "$(echo "$out" | jqv 'd["stdout"].strip()')" "hello"

# timeout -> exit 124 in result
out=$(python3 "$REPO_ROOT/tools/run-shell/run_shell.py" "sleep 5" --timeout-ms 500)
assert_eq "$(echo "$out" | jqv 'd["exit"]')" "124"

# truncation
out=$(python3 "$REPO_ROOT/tools/run-shell/run_shell.py" "seq 1 5000" --max-bytes 200)
assert_eq "$(echo "$out" | jqv 'd["truncated"]')" "True"

echo "run-shell OK"
