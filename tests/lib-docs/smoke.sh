#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

L="$REPO_ROOT/tools/lib-docs/lib_docs.py"

# unknown library -> exit 2 (deterministic when docset list loads; if
# network is down docs.json fetch dies at 1 — tolerate either)
rc=0
python3 "$L" docs zzz-no-such-lib-xyz "q" >/dev/null 2>&1 || rc=$?
{ [ "$rc" -eq 2 ] || [ "$rc" -eq 1 ]; } || fail "expected exit 2/1 for unknown lib, got $rc"

# live queries — best-effort (network-dependent)
out=$(python3 "$L" libraries python 2>/dev/null || true)
if [ -n "$out" ]; then
  assert_contains '"slug"' "$out"
  assert_contains 'python' "$out"

  out=$(python3 "$L" docs python "pathlib" --max 3 2>/dev/null || true)
  if [ -n "$out" ]; then
    assert_contains '"path"' "$out"
    assert_contains 'devdocs.io' "$out"
  fi
else
  echo "note: live DevDocs queries skipped (no network)" >&2
fi

echo "lib-docs OK"
