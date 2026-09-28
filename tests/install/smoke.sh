#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
dst="$TEST_TMPDIR/installed"

# subset copy-install, no deps — fully offline
out=$(python3 "$REPO_ROOT/tools/install/install_tool.py" --prefix "$dst" --tools file-read --no-deps --quiet)
assert_contains '"installed"' "$out"
assert_file "$dst/tools/file-read/file_read.py"
assert_file "$dst/tools/ape/ape.py"          # always included
assert_file "$dst/tools/list-tools/list_tools.py"
assert_no_file "$dst/tests"                # tests stay out of installs
assert_no_file "$dst/.git"

# installed dispatcher runs a tool from a foreign cwd
seq 1 5 > "$TEST_TMPDIR/f.txt"
out=$(cd "$TEST_TMPDIR" && "$dst/bin/ape" file-read f.txt --head 2)
assert_contains $'2\t2' "$out"

# existing prefix without --update refuses to overwrite
if python3 "$REPO_ROOT/tools/install/install_tool.py" --prefix "$dst" --tools file-read --no-deps --quiet 2>/dev/null; then
  fail "expected refusal to overwrite existing prefix without --update"
fi

# --update replaces the payload cleanly
python3 "$REPO_ROOT/tools/install/install_tool.py" --prefix "$dst" --tools file-info --no-deps --update --quiet >/dev/null
assert_file "$dst/tools/file-info/file_info.py"
assert_no_file "$dst/tools/file-read/file_read.py"

echo "install OK"
