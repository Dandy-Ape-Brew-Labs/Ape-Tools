#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

L="$REPO_ROOT/tools/logs-query/logs_query.py"
LOG="$TEST_TMPDIR/app.log"
cat > "$LOG" <<'EOF'
2026-01-01T10:00:00 INFO startup complete
2026-01-01T10:01:00 DEBUG cache warm
2026-01-01T10:02:00 ERROR db timeout connecting
2026-01-01T10:02:01 INFO retry succeeded
2026-01-01T10:03:00 WARN disk almost full
EOF

out=$(python3 "$L" file "$LOG" --level ERROR)
assert_contains 'db timeout' "$out"
assert_not_contains 'startup complete' "$out"

out=$(python3 "$L" file "$LOG" --grep "retry")
assert_contains 'retry succeeded' "$out"
assert_eq "$(echo "$out" | jqv 'd["matched"]')" "1"

out=$(python3 "$L" file "$LOG" --grep "ERROR" -C 1)
assert_contains 'cache warm' "$out"
assert_contains 'retry succeeded' "$out"

out=$(python3 "$L" file "$LOG" --since "2026-01-01T10:02:30")
assert_contains 'disk almost full' "$out"
assert_not_contains 'startup complete' "$out"
