# fs-list

Directory orientation. One level by default; `--tree` gives a
depth-limited recursive map. `.git`, `node_modules`, `.venv`, `dist` etc.
are always pruned; hidden files need `--all`.

```sh
fs_list.py src
fs_list.py . --tree --depth 2
```

Cap output with `--depth`/`--max` — don't recurse a whole disk. Then use
`fs-glob`/`code-grep` for targeting.
