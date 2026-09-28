#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

S="$REPO_ROOT/tools/semantic-search/semantic_search.py"

# deterministic embedding stub
python3 "$REPO_ROOT/tests/_fixtures/embed_stub.py" "$TEST_TMPDIR/port" &
STUB=$!
trap 'kill $STUB 2>/dev/null' EXIT
for _ in $(seq 50); do [ -s "$TEST_TMPDIR/port" ] && break; sleep 0.1; done
[ -s "$TEST_TMPDIR/port" ] || fail "embed stub did not start"
export LLM_BASE_URL="http://127.0.0.1:$(cat "$TEST_TMPDIR/port")/v1"

# fixture repo
mkdir -p "$TEST_TMPDIR/repo"
cat > "$TEST_TMPDIR/repo/alpha.py" <<'PY'
def zebra_quixotic_pancake():
    """Waffle nimbus trapezoid."""
    return 42
PY
cat > "$TEST_TMPDIR/repo/beta.py" <<'PY'
def ordinary_add(a, b):
    return a + b
PY

out=$(python3 "$S" index "$TEST_TMPDIR/repo")
assert_contains '"indexed": 2' "$out"

# idempotent reindex
out=$(python3 "$S" index "$TEST_TMPDIR/repo")
assert_contains '"skipped_unchanged": 2' "$out"

out=$(python3 "$S" query "zebra_quixotic_pancake" --k 3)
assert_contains 'alpha.py' "$out"
top=$(echo "$out" | jqv 'd["results"][0]["path"]')
assert_contains 'alpha.py' "$top"

out=$(python3 "$S" stats)
assert_contains '"chunks"' "$out"

out=$(python3 "$S" clear)
assert_contains '"cleared": true' "$out"

# unreachable endpoint -> exit 3
rc=0
LLM_BASE_URL="http://127.0.0.1:1/v1" python3 "$S" index "$TEST_TMPDIR/repo" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 3 ] || fail "expected exit 3 with dead endpoint, got $rc"

echo "semantic-search OK"
