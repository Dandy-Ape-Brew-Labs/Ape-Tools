# ask-user

File-handoff bridge to a human — the agent never blocks a tty. `ask`
writes a question file and a desktop notification, then polls for an
answer file until `--timeout` (default 30 min). Anyone (human in a
terminal, another agent, a watcher script) can `answer` it.

```sh
# agent side (blocks up to timeout, exit 3 if unanswered)
ask_user.py ask --question "Ship v2?" --options "yes,no" --timeout 600

# human side, in any shell
ask_user.py list --pending
ask_user.py answer <id> --option 1
```

Files: `$AGENT_TOOLS_HOME/questions/<id>.json`, `answers/<id>.json`.
For non-blocking checks use `list --pending` instead of `ask`'s polling.
