# knowledge

Your own searchable corpus. `add` indexes documents into a named store
(sqlite vectors under `$AGENT_TOOLS_HOME/knowledge/`); `query` returns
the top chunks with `source` path + `heading` so answers stay citable.

```sh
knowledge.py add project-docs ~/repos/project/docs
knowledge.py add notes ~/notes
knowledge.py query "how does the retry backoff work" --k 5
knowledge.py query "release process" --store project-docs
knowledge.py list
```

- Chunking splits on markdown headings (heading kept for citation) with
  ~1200-char windows and overlap.
- `.pdf` files extract via `pdftotext` when installed, skipped otherwise.
- Embeddings come from `LLM_BASE_URL` (see `semantic-search`); set
  `AGENT_EMBED_MODEL` to pin a model.
- Querying `--store '*'` (default) merges hits across all stores.
