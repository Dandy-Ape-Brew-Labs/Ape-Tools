#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

M="$REPO_ROOT/tools/memory/memory.py"
python3 "$M" create test-mem.md --text "line one" >/dev/null
out=$(python3 "$M" list)
assert_contains 'test-mem.md' "$out"

out=$(python3 "$M" view test-mem.md)
assert_contains 'line one' "$out"

python3 "$M" str_replace test-mem.md --old "one" --new "uno" >/dev/null
out=$(python3 "$M" view test-mem.md)
assert_contains 'line uno' "$out"

python3 "$M" insert test-mem.md --line 1 --text "second line" >/dev/null
out=$(python3 "$M" view test-mem.md)
assert_contains 'second line' "$out"

# duplicate create must fail
if python3 "$M" create test-mem.md --text "x" 2>/dev/null; then
  fail "expected duplicate create to fail"
fi
python3 "$M" rename test-mem.md renamed.md >/dev/null
out=$(python3 "$M" list)
assert_contains 'renamed.md' "$out"
python3 "$M" delete renamed.md >/dev/null
out=$(python3 "$M" list)
assert_not_contains 'renamed.md' "$out"
