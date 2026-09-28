"""Image search — zero-key DuckDuckGo images, or Brave with BRAVE_API_KEY.

  image_search.py "arduino wiring diagram" --max 8
  image_search.py "esp32 pinout" --backend ddg
  BRAVE_API_KEY=... image_search.py "pcb layout" --backend brave

auto = brave when the key exists, else ddg. DDG flow: fetch the result
page, extract the vqd token, then query i.js. Unofficial — may break;
use --backend brave for stability.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) agent-tools/1.0"}


def get(url: str, headers: dict | None = None, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout).read()


def search_ddg(query: str, maxn: int) -> list[dict]:
    html = get("https://duckduckgo.com/?q=" + urllib.parse.quote(query))
    m = re.search(r"vqd=['\"]?([\d-]+)['\"]?", html.decode("utf-8", "replace"))
    if not m:
        agentlib.die("could not extract DDG vqd token — layout changed "
                     "or rate-limited; try --backend brave", 1)
    url = ("https://duckduckgo.com/i.js?l=us-en&o=json&q="
           + urllib.parse.quote(query) + "&vqd=" + m.group(1))
    data = json.loads(get(url, headers={
        "Referer": "https://duckduckgo.com/"}))
    return [{"title": r.get("title"), "image_url": r.get("image"),
             "thumb_url": r.get("thumbnail"), "source_url": r.get("url"),
             "width": r.get("width"), "height": r.get("height")}
            for r in data.get("results", [])[:maxn]]


def search_brave(query: str, maxn: int) -> list[dict]:
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        agentlib.die("BRAVE_API_KEY not set", 2)
    url = ("https://api.search.brave.com/res/v1/images/search?q="
           + urllib.parse.quote(query) + f"&count={maxn}")
    data = json.loads(get(url, headers={
        "X-Subscription-Token": key,
        "Accept": "application/json"}))
    out = []
    for r in data.get("results", []):
        props = r.get("properties", {}) or {}
        thumb = r.get("thumbnail", {}) or {}
        out.append({"title": r.get("title"),
                    "image_url": props.get("url"),
                    "thumb_url": thumb.get("src"),
                    "source_url": r.get("url"),
                    "width": props.get("width"),
                    "height": props.get("height")})
    return out


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("query", nargs="+")
    p.add_argument("--max", type=int, default=10)
    p.add_argument("--backend", choices=["auto", "ddg", "brave"],
                   default="auto")
    args = p.parse_args()
    query = " ".join(args.query)

    backend = args.backend
    if backend == "auto":
        backend = "brave" if os.environ.get("BRAVE_API_KEY") else "ddg"
    try:
        results = {"ddg": search_ddg, "brave": search_brave}[backend](
            query, args.max)
    except SystemExit:
        raise
    except Exception as exc:
        agentlib.die(f"{backend} image search failed: {exc}", 1)

    agentlib.emit({"query": query, "backend": backend,
                   "count": len(results), "results": results})
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
