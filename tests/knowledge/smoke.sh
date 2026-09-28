#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

K="$REPO_ROOT/tools/knowledge/knowledge.py"

python3 "$REPO_ROOT/tests/_fixtures/embed_stub.py" "$TEST_TMPDIR/port" &
STUB=$!
trap 'kill $STUB 2>/dev/null' EXIT
for _ in $(seq 50); do [ -s "$TEST_TMPDIR/port" ] && break; sleep 0.1; done
[ -s "$TEST_TMPDIR/port" ] || fail "embed stub did not start"
export LLM_BASE_URL="http://127.0.0.1:$(cat "$TEST_TMPDIR/port")/v1"

mkdir -p "$TEST_TMPDIR/docs"
cat > "$TEST_TMPDIR/docs/guide.md" <<'MD'
# Deployment

## Rollback procedure

Invoke plaid_zebra_rollback with the previous release tag.

## Monitoring

Watch the flapdoodle metric.
MD
cat > "$TEST_TMPDIR/docs/notes.txt" <<'TXT'
ordinary shopping list: milk, eggs, flour
TXT

out=$(python3 "$K" add docs "$TEST_TMPDIR/docs")
assert_contains '"indexed": 2' "$out"

out=$(python3 "$K" query "plaid_zebra_rollback" --k 3)
assert_contains 'guide.md' "$out"
assert_contains 'Rollback procedure' "$out"

out=$(python3 "$K" list)
assert_contains '"docs"' "$out"

out=$(python3 "$K" stats docs)
assert_contains '"chunks"' "$out"

out=$(python3 "$K" remove docs)
assert_contains '"removed": "docs"' "$out"

# missing store -> exit 2
rc=0
python3 "$K" stats nope >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] || fail "expected exit 2 for missing store, got $rc"

echo "knowledge OK"
