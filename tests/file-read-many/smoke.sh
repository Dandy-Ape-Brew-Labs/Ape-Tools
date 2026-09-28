#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
mkdir -p docs
echo "alpha" > docs/a.md
echo "beta" > docs/b.md

out=$(python3 "$REPO_ROOT/tools/file-read-many/file_read_many.py" --root docs --include "*.md" --no-numbers)
assert_contains "alpha" "$out"
assert_contains "beta" "$out"
assert_contains "a.md" "$out"

# bare dir warns and fails
if python3 "$REPO_ROOT/tools/file-read-many/file_read_many.py" docs 2>/dev/null; then
  fail "expected failure on bare directory"
fi

echo "file-read-many OK"
