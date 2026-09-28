"""Library documentation lookup via DevDocs docsets — zero-key,
Context7-style. 836 docsets, cached locally under
$AGENT_TOOLS_HOME/lib-docs/.

  lib_docs.py libraries [filter]              # available docsets
  lib_docs.py docs requests "session"         # ranked index entries
  lib_docs.py docs python "pathlib glob" --excerpt
  lib_docs.py page python library/pathlib     # full page text (stdout)

Data model: devdocs.io/docs.json lists docsets; documents.devdocs.io
serves per-docset index.json (entries) and db.json (page bodies).
Docs list cached 24h; db.json revalidated against docset mtime.
"""

import gzip
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

DOCS_URL = "https://devdocs.io/docs.json"
DATA_URL = "https://documents.devdocs.io"
SITE_URL = "https://devdocs.io"
DOCS_TTL = 24 * 3600
UA = {"User-Agent": "agent-tools/1.0 (lib-docs)",
      "Accept-Encoding": "gzip"}


def cache_dir() -> Path:
    return agentlib.state_dir("lib-docs")


def get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def docsets(refresh: bool = False) -> list[dict]:
    path = cache_dir() / "docs.json"
    if (not refresh and path.exists()
            and time.time() - path.stat().st_mtime < DOCS_TTL):
        return agentlib.read_json(path, [])
    try:
        data = json.loads(get(DOCS_URL))
    except Exception as exc:
        if path.exists():
            return agentlib.read_json(path, [])
        agentlib.die(f"cannot fetch DevDocs list: {exc}", 1)
    agentlib.write_json(path, data)
    return data


def resolve(lib: str, sets: list[dict]) -> dict | None:
    lib = lib.lower()
    for s in sets:
        if s["slug"] == lib:
            return s
    named = [s for s in sets
             if s["name"].lower() == lib
             or (s.get("alias") or "").lower() == lib]
    if named:
        named.sort(key=lambda s: ("~" in s["slug"],
                                  -(s.get("mtime") or 0)))
        return named[0]
    pref = [s for s in sets if s["slug"].startswith(lib)]
    if pref:
        return min(pref, key=lambda s: len(s["slug"]))
    return None


def doc_db(slug: str, mtime: int | None) -> dict:
    """Load (and cache) a docset's db.json: {path: html}."""
    db_path = cache_dir() / f"{slug}.db.json"
    meta_path = cache_dir() / f"{slug}.mtime"
    cached_mtime = int(meta_path.read_text()) if meta_path.exists() else -1
    if db_path.exists() and mtime is not None and cached_mtime == mtime:
        return agentlib.read_json(db_path, {})
    try:
        data = json.loads(get(f"{DATA_URL}/{slug}/db.json", timeout=120))
    except Exception as exc:
        if db_path.exists():
            return agentlib.read_json(db_path, {})
        agentlib.die(f"cannot fetch {slug} db: {exc}", 1)
    agentlib.write_json(db_path, data)
    meta_path.write_text(str(mtime or 0))
    return data


def doc_index(slug: str) -> list[dict]:
    try:
        data = json.loads(get(f"{DATA_URL}/{slug}/index.json"))
    except Exception as exc:
        agentlib.die(f"cannot fetch {slug} index: {exc}", 1)
    return data.get("entries", [])


class Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def strip(html: str) -> str:
    s = Stripper()
    s.feed(html or "")
    return re.sub(r"[ \t]+", " ", " ".join(s.parts)).strip()


def rank(entries: list[dict], query: str) -> list[dict]:
    toks = [t.lower() for t in query.split() if t]
    scored = []
    for e in entries:
        name = e["name"].lower()
        hits = sum(1 for t in toks if t in name or t in e["path"].lower())
        if hits == len(toks) or (len(toks) == 1 and hits):
            scored.append((-hits, len(e["name"]), e))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [e for _, _, e in scored]


def cmd_docs(args) -> int:
    spec = resolve(args.library, docsets())
    if spec is None:
        close = [s["slug"] for s in docsets()
                 if args.library.lower() in s["slug"]][:10]
        agentlib.die(f"no docset for '{args.library}' — "
                     f"closest slugs: {close or 'none'}", 2)
    slug = spec["slug"]
    entries = doc_index(slug)
    hits = rank(entries, args.query)[:args.max] if args.query else entries[:args.max]
    db = doc_db(slug, spec.get("mtime")) if args.excerpt else {}
    out = []
    for e in hits:
        item = {"name": e["name"], "type": e.get("type"),
                "path": e["path"],
                "url": f"{SITE_URL}/{slug}/{e['path']}"}
        if args.excerpt:
            page = db.get(e["path"].split("#")[0], "")
            item["excerpt"] = strip(page)[:300]
        out.append(item)
    agentlib.emit({"library": {"name": spec["name"], "slug": slug,
                               "version": spec.get("version"),
                               "release": spec.get("release")},
                   "query": args.query, "count": len(out),
                   "results": out})
    return 0 if out else 1


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("libraries"); l.add_argument("filter", nargs="?")
    l.add_argument("--refresh", action="store_true")
    d = sub.add_parser("docs")
    d.add_argument("library"); d.add_argument("query", nargs="?")
    d.add_argument("--max", type=int, default=10)
    d.add_argument("--excerpt", action="store_true",
                   help="also fetch db.json and include text excerpts")
    pg = sub.add_parser("page")
    pg.add_argument("library"); pg.add_argument("path")
    args = p.parse_args()

    if args.cmd == "libraries":
        sets = docsets(refresh=args.refresh)
        if args.filter:
            f = args.filter.lower()
            sets = [s for s in sets
                    if f in s["slug"] or f in s["name"].lower()
                    or f in (s.get("alias") or "").lower()]
        agentlib.emit([{"name": s["name"], "slug": s["slug"],
                        "version": s.get("version"), "alias": s.get("alias")}
                       for s in sets])
        return 0

    if args.cmd == "docs":
        return cmd_docs(args)

    if args.cmd == "page":
        spec = resolve(args.library, docsets())
        if spec is None:
            agentlib.die(f"no docset for '{args.library}'", 2)
        db = doc_db(spec["slug"], spec.get("mtime"))
        page = db.get(args.path.split("#")[0])
        if page is None:
            agentlib.die(
                f"path '{args.path}' not in {spec['slug']} — "
                "find paths via: lib_docs.py docs <lib> <query>", 2)
        agentlib.emit_text(strip(page))
        return 0


if __name__ == "__main__":
    sys.exit(main())
