#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

S="$REPO_ROOT/tools/sys-info/sys_info.py"

out=$(python3 "$S")
assert_contains '"cpu"' "$out"
assert_contains '"mem"' "$out"
assert_contains '"disk"' "$out"
assert_contains '"cores"' "$out"

out=$(python3 "$S" mem)
assert_contains '"total"' "$out"

out=$(python3 "$S" bogus 2>/dev/null) && fail "expected usage error on bad section"

echo "sys-info OK"
