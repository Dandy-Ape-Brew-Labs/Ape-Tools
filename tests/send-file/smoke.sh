#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

F="$REPO_ROOT/tools/send-file/send_file.py"

echo "payload" > "$TEST_TMPDIR/payload.txt"

out=$(python3 "$F" send "$TEST_TMPDIR/payload.txt" --name report.txt)
assert_contains '"delivered"' "$out"
dest=$(echo "$out" | jqv 'd["delivered"]')
assert_file "$dest"
assert_contains 'payload' "$(cat "$dest")"

# notify outbox integration: record appended
out=$(python3 "$REPO_ROOT/tools/notify/notify.py" outbox)
assert_contains 'report.txt' "$out"

out=$(python3 "$F" list)
assert_contains 'report.txt' "$out"

# missing source -> exit 2
rc=0
python3 "$F" send "$TEST_TMPDIR/nope.bin" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] || fail "expected exit 2 for missing file, got $rc"

echo "send-file OK"
