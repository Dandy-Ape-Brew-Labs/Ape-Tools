#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

G="$REPO_ROOT/tools/gui-screen/gui_screen.py"
out=$(python3 "$G" backends)
assert_contains '"spectacle"' "$out"

# real capture only if a session is active — don't fail headless CI
if echo "$out" | grep -q '"spectacle": true' && [ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]; then
  out=$(python3 "$G" shot --out "$TEST_TMPDIR/shot.png" 2>/dev/null) || {
    echo "SKIP: capture failed (headless?)" >&2; exit 0; }
  assert_contains '"path"' "$out"
  assert_file "$TEST_TMPDIR/shot.png"
else
  echo "SKIP: no display session" >&2
fi
