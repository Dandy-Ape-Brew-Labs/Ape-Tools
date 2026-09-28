#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

P="$REPO_ROOT/tools/paper-search/paper_search.py"

# usage error: no query
if python3 "$P" 2>/dev/null; then
  fail "expected usage error on empty query"
fi

# live arXiv query — best-effort (network-dependent)
out=$(python3 "$P" "attention is all you need" --source arxiv --max 3 2>/dev/null || true)
if [ -n "$out" ]; then
  assert_contains '"source": "arxiv"' "$out"
  assert_contains '"url"' "$out"
else
  echo "note: live arXiv query skipped (no network)" >&2
fi

echo "paper-search OK"
