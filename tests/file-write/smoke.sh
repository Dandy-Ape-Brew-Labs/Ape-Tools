#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"

out=$(python3 "$REPO_ROOT/tools/file-write/file_write.py" sub/dir/new.txt --content "hello")
assert_file sub/dir/new.txt
assert_eq "$(echo "$out" | jqv 'd["action"]')" "created"

# refuse overwrite without --force
if python3 "$REPO_ROOT/tools/file-write/file_write.py" sub/dir/new.txt --content "x" 2>/dev/null; then
  fail "expected refusal without --force"
fi
python3 "$REPO_ROOT/tools/file-write/file_write.py" sub/dir/new.txt --content "x" --force >/dev/null
assert_eq "$(cat sub/dir/new.txt)" "x"

# append works without force
echo "y" | python3 "$REPO_ROOT/tools/file-write/file_write.py" sub/dir/new.txt - --append >/dev/null
assert_eq "$(cat sub/dir/new.txt)" "xy"

echo "file-write OK"
