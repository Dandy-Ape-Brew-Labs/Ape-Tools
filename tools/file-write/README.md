# file-write

Create a file or rewrite it wholesale. For targeted changes to existing
files prefer `file-edit` — smaller payload, reviewable diff.

```sh
file_write.py notes/new.md --content "# hello"
echo "line" | file_write.py out.txt -
file_write.py app.py --content "$(cat new.py)" --force
```

- Parent directories are created automatically.
- Existing files require `--force` (the error tells you to read first).
- `--append` adds to the end without requiring `--force`.
