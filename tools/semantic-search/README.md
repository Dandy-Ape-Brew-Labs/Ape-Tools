# semantic-search

Natural-language code search: "where is auth handled" → ranked code
chunks. Embeddings come from `LLM_BASE_URL` (LM Studio or any
OpenAI-compatible `/v1/embeddings`); vectors live in a local sqlite
store — nothing leaves the machine except the embedding calls.

```sh
semantic_search.py index ~/repos/myproject
semantic_search.py query "token refresh retry logic" --k 5
semantic_search.py stats
```

- `index` is incremental: files are re-embedded only when their content
  hash changes; vanished files are pruned.
- Python files chunk at top-level def/class boundaries; other files use
  100-line windows with overlap.
- Set `AGENT_EMBED_MODEL` to pin the model; otherwise the first
  `*embed*` model on `/v1/models` is used.
- Best alongside `code-grep`: semantic hits are candidates — verify with
  an exact search.
