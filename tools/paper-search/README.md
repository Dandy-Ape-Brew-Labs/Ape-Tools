# paper-search

Peer-reviewed literature without keys: PubMed (eutils), arXiv API, and
Semantic Scholar's public graph endpoint.

```sh
paper_search.py "retrieval augmented generation" --max 5
paper_search.py "graph neural networks" --source arxiv --year-min 2024
paper_search.py "metformin longevity" --source pubmed
```

- `all` (default) queries every source and dedupes by normalized title;
  per-source failures land in `errors` instead of aborting.
- Records carry `id` (PMID / arXiv id / S2 paperId), `doi`, `url`, and
  `pdf` where the source exposes one — feed `url`/`pdf` to `web-fetch`
  or `file-media` for the full text.
- Semantic Scholar is keyless but throttled; set `S2_API_KEY` for
  headroom.
