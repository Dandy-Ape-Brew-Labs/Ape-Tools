#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

A="$REPO_ROOT/tools/ask-user/ask_user.py"

# ask in background, answer it, verify roundtrip
python3 "$A" ask --question "pick one" --options "alpha,beta" \
  --timeout 30 --no-notify >"$TEST_TMPDIR/ask_out.json" 2>/dev/null &
ASK_PID=$!
sleep 0.5

qid=$(python3 "$A" list --pending | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
python3 "$A" answer "$qid" --option 2 >/dev/null

wait $ASK_PID || fail "ask did not exit 0 after answer"
out=$(cat "$TEST_TMPDIR/ask_out.json")
assert_contains '"answer": "beta"' "$out"

# timeout path
start=$(date +%s)
if python3 "$A" ask --question "nobody answers" --timeout 2 --no-notify >/dev/null 2>&1; then
  fail "expected timeout exit 3"
else
  [ $? -eq 3 ] || fail "expected exit 3"
fi
