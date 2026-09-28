#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

C="$REPO_ROOT/tools/clipboard/clipboard.py"

out=$(python3 "$C" backends)
assert_contains '"available"' "$out"

if echo "$out" | jqv 'd["selected"] is not None' | grep -q True; then
  # a backend binary exists — roundtrip is best-effort (needs a session)
  if python3 "$C" set "agent-tools-smoke" >/dev/null 2>&1; then
    out=$(python3 "$C" get)
    assert_contains 'agent-tools-smoke' "$out"
  else
    echo "note: backend installed but no live session, skipping roundtrip" >&2
  fi
else
  rc=0
  python3 "$C" get >/dev/null 2>&1 || rc=$?
  [ "$rc" -eq 3 ] || fail "expected exit 3 without a backend, got $rc"
fi

echo "clipboard OK"
