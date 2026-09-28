#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

D="$REPO_ROOT/tools/diff/diff_tool.py"
mkdir -p "$TEST_TMPDIR/one" "$TEST_TMPDIR/two"
printf 'alpha\nbeta\ngamma\n' > "$TEST_TMPDIR/one/f.txt"
printf 'alpha\nBETA\ngamma\n' > "$TEST_TMPDIR/two/f.txt"
cp "$TEST_TMPDIR/one/f.txt" "$TEST_TMPDIR/same.txt"

# identical -> 0, empty output
out=$(python3 "$D" "$TEST_TMPDIR/one/f.txt" "$TEST_TMPDIR/same.txt")
[ -z "$out" ] || fail "expected empty output for identical files"

# different -> 1, diff body present
rc=0
out=$(python3 "$D" "$TEST_TMPDIR/one/f.txt" "$TEST_TMPDIR/two/f.txt") || rc=$?
[ "$rc" -eq 1 ] || fail "expected exit 1 for differing files, got $rc"
assert_contains 'BETA' "$out"
assert_contains '-beta' "$out"

# --stat -> JSON summary
rc=0
out=$(python3 "$D" "$TEST_TMPDIR/one" "$TEST_TMPDIR/two" --recursive --stat) || rc=$?
[ "$rc" -eq 1 ] || fail "expected exit 1 for differing dirs, got $rc"
assert_contains '"changed_files"' "$out"

# missing path -> 2
rc=0
python3 "$D" "$TEST_TMPDIR/nope" "$TEST_TMPDIR/same.txt" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] || fail "expected exit 2 for missing path, got $rc"

echo "diff OK"
