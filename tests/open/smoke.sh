#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

O="$REPO_ROOT/tools/open/open.py"

echo "hello" > "$TEST_TMPDIR/f.txt"

if command -v xdg-mime >/dev/null; then
  out=$(python3 "$O" mime "$TEST_TMPDIR/f.txt")
  assert_contains '"mime"' "$out"
else
  echo "note: xdg-mime missing, skipping mime check" >&2
fi

# missing file -> exit 2
rc=0
python3 "$O" open "$TEST_TMPDIR/nope.bin" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] || fail "expected exit 2 for missing file, got $rc"

# open: live desktop only, tolerate headless
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  rc=0
  python3 "$O" open "$TEST_TMPDIR/f.txt" >/dev/null 2>&1 || rc=$?
  [ "$rc" -eq 3 ] || fail "expected exit 3 headless, got $rc"
else
  python3 "$O" open "$TEST_TMPDIR/f.txt" >/dev/null \
    || echo "note: xdg-open failed in this session" >&2
fi

echo "open OK"
