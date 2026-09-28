# send-file

A file sitting in the sandbox is invisible to the user — `send` fixes
that: copies it into `$AGENT_TOOLS_HOME/outbox/files/`, shows a desktop
notification with the path, and records the delivery in the outbox so
`notify.py outbox` lists it too. Headless-safe: the record persists even
when `notify-send` is missing.

```sh
send_file.py send build/report.pdf --title "Report ready" --open
send_file.py list
```

For sharing with *other machines/people* on the LAN, see `serve`.
