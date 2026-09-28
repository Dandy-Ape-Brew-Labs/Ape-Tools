# plan-todo

File-backed plan state for multi-step tasks (≥3 steps). Exactly one item
`in_progress`; mark `completed` immediately on finishing; make the last
item verification.

```sh
plan_todo.py set --todos '[{"content":"add flag","status":"in_progress"},{"content":"run tests","status":"pending"}]'
plan_todo.py complete 1
plan_todo.py list
```

Stored at `$AGENT_TOOLS_HOME/todos.json` — survives context compaction
and session restarts, so `list` re-syncs the plan anytime.
