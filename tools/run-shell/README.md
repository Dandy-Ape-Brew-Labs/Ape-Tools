# run-shell

Run a command, get JSON `{exit, stdout, stderr, duration_ms, truncated}`.

```sh
run_shell.py "pytest -x -q" --timeout-ms 300000
run_shell.py "make" --cwd /repo
```

- Always pass `--timeout-ms`; a hanging command returns exit 124 in the
  JSON (the tool itself exits 0 — check the `exit` field).
- Output truncates head+tail past `--max-bytes`.
- Long-lived processes (servers, watchers): use `proc` instead.
- Interactive programs will block until timeout — put `-y`/`--no-input`/
  `CI=1` in the command.
