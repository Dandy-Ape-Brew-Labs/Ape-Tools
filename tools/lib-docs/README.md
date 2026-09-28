# lib-docs

Current library docs instead of stale training data — DevDocs' 836
docsets (Python, React, NumPy, Rust, …), zero-key.

```sh
lib_docs.py libraries python            # find the docset slug
lib_docs.py docs requests "session"     # ranked index entries + URLs
lib_docs.py docs python "pathlib" --excerpt
lib_docs.py page python library/pathlib # full page text
```

- Resolution: exact slug → name/alias (latest version preferred) →
  slug prefix; unknown names list the closest slugs.
- `docs` is cheap (index.json only). `--excerpt` and `page` fetch the
  docset's `db.json` once and cache it under
  `$AGENT_TOOLS_HOME/lib-docs/`, revalidated against docset mtime.
- DevDocs is community-maintained and usually a few releases behind;
  for bleeding-edge, follow the entry's `url` with `web-fetch`.
