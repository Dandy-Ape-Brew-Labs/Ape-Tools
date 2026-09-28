# file-watch

"Wait until the artifact appears" as a blocking call — or stream file
events as JSON lines while something else works.

```sh
file_watch.py dist/app.bin --once           # block until it exists/changes
file_watch.py src/ --timeout 10             # events for 10s, then exit
file_watch.py . --events created --once     # next new file, then done
```

- Polling (mtime+size) — portable, no inotify/dependency.
- `--once` exits `0` on the first event: the canonical "wait-for"
  gate. Run it after `proc start`/`serve start` to sync on output.
- Long-running watchers pair naturally with `proc` — start it in the
  background and read the event stream from the proc's log file.
- SIGTERM/SIGINT stop cleanly; `--timeout` bounds unattended waits.
