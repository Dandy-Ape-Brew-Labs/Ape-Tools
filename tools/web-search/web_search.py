"""Web search. Zero-key default: DuckDuckGo lite HTML. API backends when
TAVILY_API_KEY or BRAVE_API_KEY are set (or --backend forces one).

  web_search.py "python walrus operator" --max 5
  web_search.py "release notes" --allowed-domains docs.python.org
  TAVILY_API_KEY=... web_search.py "x" --backend tavily
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) agent-tools/1.0"}


class DDGLiteParser(HTMLParser):
    """Parse html.duckduckgo.com result links."""

    def __init__(self):
        super().__init__()
        self.results = []
        self._in_link = False
        self._cur = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "result-link" in attrs.get("class", ""):
            self._in_link = True
            self._cur = {"url": attrs.get("href", ""), "title": ""}
        elif tag == "td" and "result-snippet" in attrs.get("class", ""):
            self._in_snip = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_link:
            self._in_link = False
            if self._cur and self._cur["url"]:
                self.results.append(self._cur)
            self._cur = None

    def handle_data(self, data):
        if self._in_link and self._cur is not None:
            self._cur["title"] += data.strip()


def unwrap_ddg(url: str) -> str:
    """DDG wraps links as //duckduckgo.com/l/?uddg=<encoded>."""
    if "uddg=" in url:
        return urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
    return url


def search_ddg(query: str, max_results: int) -> list[dict]:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers=UA)
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    parser = DDGLiteParser()
    parser.feed(html)
    results = [
        {"title": r["title"], "url": unwrap_ddg(r["url"]), "snippet": ""}
        for r in parser.results
    ]
    return results[:max_results]


def search_tavily(query: str, max_results: int) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        agentlib.die("TAVILY_API_KEY not set", 2)
    body = json.dumps({"query": query, "max_results": max_results}).encode()
    req = urllib.request.Request(
        "https://api.tavily.com/search", data=body,
        headers={**UA, "Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    return [{"title": r.get("title"), "url": r.get("url"),
             "snippet": r.get("content", "")[:300]}
            for r in data.get("results", [])]


def search_brave(query: str, max_results: int) -> list[dict]:
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        agentlib.die("BRAVE_API_KEY not set", 2)
    url = ("https://api.search.brave.com/res/v1/web/search?q="
           + urllib.parse.quote(query) + f"&count={max_results}")
    req = urllib.request.Request(
        url, headers={**UA, "X-Subscription-Token": key})
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    return [{"title": r.get("title"), "url": r.get("url"),
             "snippet": r.get("description", "")}
            for r in data.get("web", {}).get("results", [])]


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("query", nargs="+")
    p.add_argument("--max", type=int, default=5)
    p.add_argument("--backend", choices=["auto", "ddg", "tavily", "brave"],
                   default="auto")
    p.add_argument("--allowed-domains", help="comma-separated domain filter")
    args = p.parse_args()

    query = " ".join(args.query)
    backend = args.backend
    if backend == "auto":
        if os.environ.get("TAVILY_API_KEY"):
            backend = "tavily"
        elif os.environ.get("BRAVE_API_KEY"):
            backend = "brave"
        else:
            backend = "ddg"

    fn = {"ddg": search_ddg, "tavily": search_tavily,
          "brave": search_brave}[backend]
    try:
        results = fn(query, args.max)
    except Exception as exc:
        agentlib.die(f"{backend} search failed: {exc}")

    if args.allowed_domains:
        allow = {d.strip() for d in args.allowed_domains.split(",")}
        results = [r for r in results
                   if urllib.parse.urlparse(r["url"]).hostname in allow
                   or any((urllib.parse.urlparse(r["url"]).hostname or "")
                          .endswith("." + d) for d in allow)]

    agentlib.emit({"query": query, "backend": backend,
                   "count": len(results), "results": results})
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
