#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
mkdir -p a/b
touch a/x.test.js a/b/y.test.js a/z.txt

out=$(python3 "$REPO_ROOT/tools/fs-glob/fs_glob.py" "*.test.js" --path .)
assert_eq "$(echo "$out" | jqv 'd["count"]')" "2"

out=$(python3 "$REPO_ROOT/tools/fs-glob/fs_glob.py" "z.*" --path .)
assert_eq "$(echo "$out" | jqv 'd["count"]')" "1"
echo "fs-glob OK"
