#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
printf 'one\nthree\n' > f.txt
python3 "$REPO_ROOT/tools/file-insert/file_insert.py" f.txt --line 1 --text "two" >/dev/null
assert_eq "$(sed -n 2p f.txt)" "two"
python3 "$REPO_ROOT/tools/file-insert/file_insert.py" f.txt --line 0 --text "zero" >/dev/null
assert_eq "$(head -1 f.txt)" "zero"
python3 "$REPO_ROOT/tools/file-insert/file_insert.py" f.txt --line -1 --text "end" >/dev/null
assert_eq "$(tail -1 f.txt)" "end"
echo "file-insert OK"
