# file-read-many

Batch-load files into context. Files are concatenated with
`--- {path} ---` separators, numbered lines by default. A bare directory
path matches nothing — pass a glob. `.gitignore` and common build dirs
(`node_modules`, `.venv`, `dist`, …) are respected; use `--no-gitignore`
to override.

```sh
file_read_many.py --root docs --include "*.md"
file_read_many.py "src/**/*.py" --exclude "*_test.py"
```

Binary files are skipped with a stderr note. Output is capped at 256KB
(`--max-bytes`); narrow the globs if truncated.
