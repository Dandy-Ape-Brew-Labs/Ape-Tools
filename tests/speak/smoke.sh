#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

S="$REPO_ROOT/tools/speak/speak.py"

out=$(python3 "$S" backends)
assert_contains '"available"' "$out"

if echo "$out" | jqv 'd["selected"] is not None' | grep -q True; then
  # best-effort: audio may be unavailable even when the engine exists
  python3 "$S" say "smoke" >/dev/null 2>&1 \
    || echo "note: engine present but playback failed" >&2
else
  rc=0
  python3 "$S" say "smoke" >/dev/null 2>&1 || rc=$?
  [ "$rc" -eq 3 ] || fail "expected exit 3 without engine, got $rc"
fi

# empty text -> exit 2 (when an engine exists) or 3
rc=0
printf '' | python3 "$S" say >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] || [ "$rc" -eq 3 ] || fail "expected exit 2/3 for empty text, got $rc"

echo "speak OK"
