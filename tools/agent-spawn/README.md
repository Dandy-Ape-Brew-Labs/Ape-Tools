# agent-spawn

Delegate a self-contained subtask to an installed agent CLI and get
its output back. Backends: `claude` (preferred) and `gemini`.

```sh
agent_spawn.py backends
agent_spawn.py run "Review src/auth.py for SQL injection" --cwd "$PWD"
agent_spawn.py run "Fix the bug" --dangerous   # no permission prompts
```

For parallel fan-out, run several `agent_spawn.py run` calls through
`proc start` and collect results with `proc read`.
