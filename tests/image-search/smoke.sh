#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

I="$REPO_ROOT/tools/image-search/image_search.py"

if python3 "$I" 2>/dev/null; then
  fail "expected usage error on empty query"
fi

# --backend brave without key -> exit 2 (deterministic, no network)
rc=0
env -u BRAVE_API_KEY python3 "$I" "test" --backend brave >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] || fail "expected exit 2 without BRAVE_API_KEY, got $rc"

# live DDG query — best-effort
out=$(python3 "$I" "linux penguin" --max 3 2>/dev/null || true)
if [ -n "$out" ]; then
  assert_contains '"image_url"' "$out"
else
  echo "note: live image search skipped (no network/token failure)" >&2
fi

echo "image-search OK"
