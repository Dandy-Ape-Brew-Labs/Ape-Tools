#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
mkdir -p sub/nested node_modules
touch a.txt sub/b.txt sub/nested/c.txt node_modules/x.js .hidden

out=$(python3 "$REPO_ROOT/tools/fs-list/fs_list.py" .)
assert_eq "$(echo "$out" | jqv 'd["count"]')" "2"   # a.txt + sub/ (hidden+pruned excluded)

out=$(python3 "$REPO_ROOT/tools/fs-list/fs_list.py" . --tree --depth 3)
assert_contains "c.txt" "$out"
echo "fs-list OK"
