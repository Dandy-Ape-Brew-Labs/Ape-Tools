# py-run

Run Python code — snippets (`-c`) or script files. Uses the repo's shared
`.venv` via `uv run` (declared dependencies available); `--system` uses
bare `python3`.

```sh
py_run.py -c "import json; print(json.dumps({'a':1}))"
py_run.py analysis.py input.csv --timeout 300
```

For a persistent interpreter (variables surviving between calls), use
`proc`: `proc.py start "python3 -i"` then `proc.py write <id>`.
