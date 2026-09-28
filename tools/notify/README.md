# notify

Desktop + file-outbox notifications so the human never misses an
agent reaching out (or finishing).

```sh
notify.py send --title "Tests failed" --body "3 failures in auth/"
notify.py finish --message "Migration complete"
notify.py outbox
```

Every `send`/`finish` appends a JSON record to
`$AGENT_TOOLS_HOME/outbox/` — safe on headless sessions where
`notify-send` is missing.
