#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

W="$REPO_ROOT/tools/file-watch/file_watch.py"
d="$TEST_TMPDIR/watch"
mkdir -p "$d"

# --once detects a creation
( sleep 0.4; touch "$d/newfile" ) &
out=$(python3 "$W" "$d" --once --interval 0.1 --timeout 5)
assert_contains '"event": "created"' "$out"
assert_contains 'newfile' "$out"
wait 2>/dev/null || true

# --once detects a modification
echo x > "$d/mod"
( sleep 0.4; echo y >> "$d/mod" ) &
out=$(python3 "$W" "$d" --once --interval 0.1 --timeout 5 --events modified)
assert_contains '"event": "modified"' "$out"
wait 2>/dev/null || true

# --timeout with no events exits 0 quietly
rc=0
out=$(python3 "$W" "$d" --interval 0.1 --timeout 0.3) || rc=$?
[ "$rc" -eq 0 ] || fail "timeout watch should exit 0, got $rc"
[ -z "$out" ] || fail "expected no events, got: $out"

echo "file-watch OK"
