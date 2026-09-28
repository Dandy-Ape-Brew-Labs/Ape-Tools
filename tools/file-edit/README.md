# file-edit

Exact-string replacement. `old` must match the file byte-for-byte and
uniquely. Copy `old` from a fresh `file-read` — never from memory.

```sh
file_edit.py app.py --old "TIMEOUT = 30" --new "TIMEOUT = 60"
file_edit.py app.py --old "fetchUser" --new "loadUser" --replace-all
file_edit.py app.py --edits batch.json --dry-run   # preview diff
```

Batch file format (`--edits`):

```json
[
  {"old": "a = 1", "new": "a = 2"},
  {"old": "debug", "new": "log", "replace_all": true}
]
```

Edits apply sequentially and atomically — any failure leaves the file
untouched. Errors are actionable: "not found" → re-read; "N matches" →
widen context or `--replace-all`.
