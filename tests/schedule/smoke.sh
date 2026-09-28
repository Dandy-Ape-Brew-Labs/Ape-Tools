#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

S="$REPO_ROOT/tools/schedule/schedule.py"
if ! systemctl --user list-timers >/dev/null 2>&1; then
  echo "SKIP: no systemd user manager" >&2
  exit 0
fi

out=$(python3 "$S" once --in 2h --command "true" --name smoketest)
assert_contains 'agent-tools-smoketest' "$out"

out=$(python3 "$S" list)
assert_contains 'smoketest' "$out"

python3 "$S" cancel smoketest >/dev/null
out=$(python3 "$S" list)
assert_not_contains 'smoketest' "$out"
