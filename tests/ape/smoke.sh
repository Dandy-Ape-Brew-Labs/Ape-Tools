#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
printf 'hi\n' > f.txt

# dispatch a stdlib tool from a foreign cwd
out=$(python3 "$REPO_ROOT/tools/ape/ape.py" file-read f.txt)
assert_contains $'1\thi' "$out"

# dispatch the catalogue
out=$(python3 "$REPO_ROOT/tools/ape/ape.py" --list)
assert_contains "file-read" "$out"

# unknown tool fails with usage error
if python3 "$REPO_ROOT/tools/ape/ape.py" nope 2>/dev/null; then
  fail "expected failure for unknown tool"
fi

# exit code propagates from the tool
if python3 "$REPO_ROOT/tools/ape/ape.py" file-read f.txt --start 99 2>/dev/null; then
  fail "expected file-read's failure to propagate"
fi

echo "ape OK"
