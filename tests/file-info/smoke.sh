#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
printf 'a\nb\nc\n' > f.txt
out=$(python3 "$REPO_ROOT/tools/file-info/file_info.py" f.txt)
assert_eq "$(echo "$out" | jqv 'd["lines"]')" "3"
assert_eq "$(echo "$out" | jqv 'd["size_bytes"]')" "6"
echo "file-info OK"
