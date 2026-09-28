#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"

python3 "$REPO_ROOT/tools/fs-manage/fs_manage.py" mkdir a/b/c >/dev/null
[ -d a/b/c ] || fail "mkdir failed"

echo x > f.txt
python3 "$REPO_ROOT/tools/fs-manage/fs_manage.py" move f.txt g.txt >/dev/null
assert_file g.txt; assert_no_file f.txt

python3 "$REPO_ROOT/tools/fs-manage/fs_manage.py" copy g.txt h.txt >/dev/null
assert_file h.txt; assert_file g.txt

# delete goes to trash
python3 "$REPO_ROOT/tools/fs-manage/fs_manage.py" delete h.txt >/dev/null
assert_no_file h.txt
[ -n "$(find "$AGENT_TOOLS_HOME/trash" -name '*h.txt' -print -quit)" ] || fail "not in trash"

# permanent delete
echo y > j.txt
python3 "$REPO_ROOT/tools/fs-manage/fs_manage.py" delete j.txt --permanent >/dev/null
assert_no_file j.txt

echo "fs-manage OK"
