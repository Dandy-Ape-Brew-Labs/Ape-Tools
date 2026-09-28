# schedule

Deferred/recurring execution through transient systemd user timers —
no daemon, no cron edits. Units are named `agent-tools-<name>`.

```sh
schedule.py once --in 45m --command "python3 tools/notify/notify.py send --title break"
schedule.py recurring --calendar "Mon..Fri 09:00" --command "make standup" --name standup
schedule.py list
schedule.py cancel standup
```

Limitations: transient units don't survive reboot; `--at`/`--calendar`
take systemd calendar specs. Fired commands run outside the agent's
environment (fresh systemd env).
