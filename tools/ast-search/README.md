# ast-search

Python-aware code search over the AST — find call sites, defs,
imports and references without grep's false positives (comments,
strings, similar names).

```sh
ast_search.py symbols src/                  # outline of every file
ast_search.py defs src/ --name "^test_"
ast_search.py calls src/ --name "session\.query"
ast_search.py refs src/ --name "^logger$"
ast_search.py imports . --name "requests"
```

Dotted call names resolve (`obj.method` → `obj.method`), so
`--name "query$"` catches `db.query(...)` too. Emits JSON
`{file,line,col,kind,name,context}` — pipe through `jq`.
