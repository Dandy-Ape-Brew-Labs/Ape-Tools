# tool-search

Tier-2 discovery: given a natural-language description of what you want to do,
returns the full manifests of the best-matching tools. Scores manifests with a
BM25-lite ranker over `name`, `use_when`, `description`, `keywords`, and args.

## Usage

```sh
python3 tools/tool-search/search.py replace a string in a file
python3 tools/tool-search/search.py --select file-edit,file-read
python3 tools/tool-search/search.py take a screenshot --names-only
```

`--select` is the fast path when you already know the name (mirrors the
`select:A,B` convention from the reference doc).

Exit codes: `0` matches found, `1` no matches, `2` usage error.
