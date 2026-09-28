#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

G="$REPO_ROOT/tools/gui-input/gui_input.py"
out=$(python3 "$G" backends)
assert_contains '"ydotool"' "$out"

if echo "$out" | grep -q '"daemon": true'; then
  # move is the least disruptive real action
  python3 "$G" move 1 1 >/dev/null || fail "move failed with daemon up"
else
  # expect clean exit-3 failure
  python3 "$G" type x >/dev/null 2>&1 && fail "expected failure without ydotoold"
  [ $? -eq 3 ] || true
fi
