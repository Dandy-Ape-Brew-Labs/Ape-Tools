# web-search

Web search → JSON results. Zero-config default scrapes DuckDuckGo lite;
set `TAVILY_API_KEY` or `BRAVE_API_KEY` for API backends.

```sh
web_search.py "python 3.14 release notes"
web_search.py "array syntax" --allowed-domains docs.python.org
```

Keep queries short (1–6 words), one fact per query. Snippets are not
sources — fetch the page with `web-fetch` (or `obscura-browse` for
JS-heavy sites) before citing a fact. On a miss, reformulate rather than
repeating the same query.
