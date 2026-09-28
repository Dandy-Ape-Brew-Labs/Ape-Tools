#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

G="$REPO_ROOT/tools/git-ops/git_ops.py"
REPO="$TEST_TMPDIR/repo"
mkdir -p "$REPO"
git -C "$REPO" init -q
git -C "$REPO" config user.email t@t && git -C "$REPO" config user.name t
echo a > "$REPO/a.txt"

out=$(python3 "$G" --cwd "$REPO" status)
assert_contains '"clean": false' "$out"

out=$(python3 "$G" --cwd "$REPO" commit --message "init" --files a.txt)
assert_contains '"committed": true' "$out"

out=$(python3 "$G" --cwd "$REPO" status)
assert_contains '"clean": true' "$out"

out=$(python3 "$G" --cwd "$REPO" log -n 5)
assert_contains '"subject": "init"' "$out"

python3 "$G" --cwd "$REPO" checkout -b feat >/dev/null
out=$(python3 "$G" --cwd "$REPO" branch)
assert_contains '"current": "feat"' "$out"

# non-repo dir must fail
if python3 "$G" --cwd "$TEST_TMPDIR" status 2>/dev/null; then
  fail "expected failure outside repo"
fi
