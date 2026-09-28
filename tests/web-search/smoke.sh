#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

# usage error: no query
if python3 "$REPO_ROOT/tools/web-search/web_search.py" 2>/dev/null; then
  fail "expected usage error on empty query"
fi

# live DDG query is best-effort (network-dependent)
out=$(python3 "$REPO_ROOT/tools/web-search/web_search.py" "python programming" --max 3 2>/dev/null || true)
if [ -n "$out" ]; then
  assert_contains '"results"' "$out"
else
  echo "note: live search skipped (no network)" >&2
fi

echo "web-search OK"
