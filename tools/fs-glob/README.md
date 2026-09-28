# fs-glob

"Where is X" by filename. Glob `*` crosses directory separators, so
`*.test.ts` finds nested matches; `**/config.*` also works.

```sh
fs_glob.py "*.py" --path src
fs_glob.py "**/tool.json" --max 50
```

Results sort by modification time, newest first. `.gitignore` is
respected — pass `--no-gitignore` to include ignored files.
