#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

S="$REPO_ROOT/tools/secrets/secrets.py"
vault="$AGENT_TOOLS_HOME/secrets.json"

# check runs and never crashes even with no vault
out=$(python3 "$S" check)
assert_contains '"name"' "$out"

# set stores via stdin; output contains the NAME, not the value
out=$(echo "supersecret-value-123" | python3 "$S" set TEST_SMOKE_KEY)
assert_contains 'TEST_SMOKE_KEY' "$out"
assert_not_contains 'supersecret-value-123' "$out"
assert_file "$vault"
[ "$(stat -c %a "$vault")" = "600" ] || fail "vault not chmod 600"

# list shows names only
out=$(python3 "$S" list)
assert_contains 'TEST_SMOKE_KEY' "$out"
assert_not_contains 'supersecret-value-123' "$out"

# run injects into child env without printing the value itself
out=$(python3 "$S" run -- python3 -c "import os; print('ok' if os.environ.get('TEST_SMOKE_KEY')=='supersecret-value-123' else 'missing')")
assert_eq "ok" "$out"

# empty stdin refused
rc=0
echo -n "" | python3 "$S" set EMPTY_KEY >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] || fail "expected exit 2 on empty secret, got $rc"

# del removes
python3 "$S" del TEST_SMOKE_KEY >/dev/null
out=$(python3 "$S" list)
assert_not_contains 'TEST_SMOKE_KEY' "$out"
rc=0
python3 "$S" del TEST_SMOKE_KEY >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 1 ] || fail "expected exit 1 deleting missing key, got $rc"

echo "secrets OK"
