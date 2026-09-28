# serve

Publish files or static artifacts over local HTTP — the "shareable
output" half of `send-file` (which notifies instead).

```sh
serve.py serve docs/site --port 8080   # http://127.0.0.1:8080/
serve.py serve out/report.pdf          # parent dir + file URL
serve.py serve exports/ --lan          # http://<lan-ip>:<port>/ (no auth!)
serve.py list
serve.py stop <proc-id>
```

- Servers run through `proc`, so `proc.py list`/`kill` manages them.
- Default bind is `127.0.0.1`; `--lan` exposes the directory to the
  whole network — use deliberately.
- `qrencode` installed → a QR of the URL prints to stderr (scan with a
  phone).
