#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
seq 1 20 | sed 's/^/line/' > f.txt

out=$(python3 "$REPO_ROOT/tools/file-read/file_read.py" f.txt --start 3 --end 5)
assert_contains $'3\tline3' "$out"
assert_contains $'5\tline5' "$out"

out=$(python3 "$REPO_ROOT/tools/file-read/file_read.py" f.txt --tail 3)
assert_contains $'20\tline20' "$out"

# out-of-range start errors
if python3 "$REPO_ROOT/tools/file-read/file_read.py" f.txt --start 99 2>/dev/null; then
  fail "expected failure for out-of-range start"
fi

# binary refusal
printf 'a\0b' > bin.dat
if python3 "$REPO_ROOT/tools/file-read/file_read.py" bin.dat 2>/dev/null; then
  fail "expected binary refusal"
fi

echo "file-read OK"
