#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

N="$REPO_ROOT/tools/notify/notify.py"
out=$(python3 "$N" send --title "smoke test" --body "hi")
assert_contains '"notified": true' "$out"

out=$(python3 "$N" outbox)
assert_contains 'smoke test' "$out"

out=$(python3 "$N" finish --message "all done")
assert_contains '"finished": true' "$out"
