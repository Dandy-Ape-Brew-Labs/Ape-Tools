# diff

"Did anything change?" as an exit code — plus the unified diff when
the answer is yes. Compares two files or two directory trees.

```sh
diff_tool.py expected.txt actual.txt
diff_tool.py build_a/ build_b/ --recursive --stat
```

- Exit `0` identical / `1` differences / `2` error — branch on `$?`
  the same way you would with `diff(1)`.
- `--stat` returns `{changed_files, files:[{file, added, removed}]}`
  for a token-cheap summary before you decide to look at the diff.
- File comparisons fall back to stdlib `difflib` when the `diff`
  binary is missing; directory comparisons require it.
