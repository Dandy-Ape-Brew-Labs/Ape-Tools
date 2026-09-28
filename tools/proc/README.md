# proc

Background processes with a file-based registry (survives the invoking
shell). Logs land in `$AGENT_TOOLS_HOME/procs/<id>/`.

```sh
proc.py start "npm run dev" --cwd /repo    # -> {"id": "...", ...}
proc.py read <id> --tail 50                # poll output
proc.py read <id> --since 2048             # only new stdout bytes
proc.py write <id> --text "y\n"            # answer a prompt
proc.py list
proc.py kill <id>
```

Use for dev servers, watchers, long builds — anything that would block a
`run-shell` call. Interactive programs can be fed via `write` (FIFO
stdin), but prefer non-interactive flags. Kill what you start; don't
leave orphans.
