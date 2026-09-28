# code-map

Top-level definitions per file — a cheap map of a module before reading it.

```sh
code_map.py src/              # JSON: file → [{line, text}]
code_map.py src/app.py        # one file
code_map.py . --map --budget 4000   # compact text repo map
```

Heuristic per-language patterns (py, js/ts, go, rs, java, kt, c/cpp, rb,
sh, lua, swift). A map for orientation, not a parser — verify hits with
`code-grep`/`file-read`.
