# logs-query

Triage-oriented log access — files and the systemd journal — with
the filters agents actually need: regex, time window, severity, tail.

```sh
logs_query.py file /var/log/app.log --level ERROR --tail 50 -C 3
logs_query.py file app.log --grep "timeout" --since "2026-09-01T00:00"
logs_query.py journal --unit sshd --priority err --since "1h ago"
logs_query.py journal --user --grep "failed" -n 200
```

File mode treats lines without a parseable ISO timestamp as
"within window" (attached to the previous entry). Journal mode
accepts native journalctl time specs like `1h ago`.
