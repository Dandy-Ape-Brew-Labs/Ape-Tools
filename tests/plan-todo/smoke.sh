#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

T=$(python3 "$REPO_ROOT/tools/plan-todo/plan_todo.py" set --todos '[{"content":"step a","status":"in_progress"},{"content":"step b"}]')
assert_contains '"saved": 2' "$T"

out=$(python3 "$REPO_ROOT/tools/plan-todo/plan_todo.py" list)
assert_contains '"id": 2' "$out"
assert_contains 'step b' "$out"

python3 "$REPO_ROOT/tools/plan-todo/plan_todo.py" complete 1 >/dev/null
out=$(python3 "$REPO_ROOT/tools/plan-todo/plan_todo.py" list)
assert_contains '"status": "completed"' "$out"

# two in_progress must fail
if python3 "$REPO_ROOT/tools/plan-todo/plan_todo.py" set --todos \
    '[{"content":"x","status":"in_progress"},{"content":"y","status":"in_progress"}]' 2>/dev/null; then
  fail "expected failure for two in_progress"
fi
python3 "$REPO_ROOT/tools/plan-todo/plan_todo.py" clear >/dev/null
out=$(python3 "$REPO_ROOT/tools/plan-todo/plan_todo.py" list)
assert_eq "$out" "[]"
