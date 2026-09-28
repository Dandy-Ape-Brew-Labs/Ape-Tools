"""Academic paper search — PubMed, arXiv, Semantic Scholar. Zero-key.

  paper_search.py "transformer quantization" --max 5
  paper_search.py "crispr off-target" --source pubmed --year-min 2023
  paper_search.py "diffusion models" --source all

PubMed eutils and the arXiv API need no key; Semantic Scholar is
keyless but rate-limited (S2_API_KEY lifts it). 'all' merges sources
and dedupes by title.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

UA = {"User-Agent": "agent-tools/1.0 (paper-search)"}
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ATOM = {"a": "http://www.w3.org/2005/Atom"}


def get(url: str, headers: dict | None = None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout).read()


def search_pubmed(query: str, maxn: int, year_min: int | None) -> list[dict]:
    term = query
    if year_min:
        term += f" AND {year_min}:3000[dp]"
    url = (f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&retmax={maxn}"
           f"&term={urllib.parse.quote(term)}")
    ids = json.loads(get(url))["esearchresult"]["idlist"]
    if not ids:
        return []
    url = (f"{EUTILS}/esummary.fcgi?db=pubmed&retmode=json"
           f"&id={','.join(ids)}")
    res = json.loads(get(url))["result"]
    out = []
    for pmid in ids:
        d = res.get(pmid, {})
        doi = next((a["value"] for a in d.get("articleids", [])
                    if a.get("idtype") == "doi"), None)
        year = (d.get("pubdate", "")[:4] or "").strip()
        out.append({
            "source": "pubmed", "id": pmid,
            "title": d.get("title", "").rstrip("."),
            "authors": [a.get("name") for a in d.get("authors", [])][:6],
            "year": int(year) if year.isdigit() else None,
            "abstract": None,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "pdf": None, "doi": doi})
    return out


def search_arxiv(query: str, maxn: int, year_min: int | None) -> list[dict]:
    url = ("https://export.arxiv.org/api/query?search_query="
           f"all:{urllib.parse.quote(query)}&max_results={maxn}"
           "&sortBy=submittedDate&sortOrder=descending")
    root = ET.fromstring(get(url))
    out = []
    for e in root.findall("a:entry", ATOM):
        aid = e.findtext("a:id", default="", namespaces=ATOM)
        published = (e.findtext("a:published", default="",
                                namespaces=ATOM) or "")[:4]
        year = int(published) if published.isdigit() else None
        if year_min and year and year < year_min:
            continue
        out.append({
            "source": "arxiv", "id": aid.split("/abs/")[-1],
            "title": " ".join(
                (e.findtext("a:title", default="",
                            namespaces=ATOM) or "").split()),
            "authors": [a.findtext("a:name", default="",
                                   namespaces=ATOM)
                        for a in e.findall("a:author", ATOM)][:6],
            "year": year,
            "abstract": " ".join(
                (e.findtext("a:summary", default="",
                            namespaces=ATOM) or "").split())[:500],
            "url": aid,
            "pdf": aid.replace("/abs/", "/pdf/") or None,
            "doi": None})
    return out


def search_s2(query: str, maxn: int, year_min: int | None) -> list[dict]:
    fields = "title,authors,year,abstract,externalIds,url,openAccessPdf"
    url = ("https://api.semanticscholar.org/graph/v1/paper/search"
           f"?query={urllib.parse.quote(query)}&limit={maxn}"
           f"&fields={fields}")
    headers = {}
    if os.environ.get("S2_API_KEY"):
        headers["x-api-key"] = os.environ["S2_API_KEY"]
    data = json.loads(get(url, headers=headers))
    out = []
    for p in data.get("data", []):
        year = p.get("year")
        if year_min and year and year < year_min:
            continue
        out.append({
            "source": "s2", "id": p.get("paperId"),
            "title": p.get("title"),
            "authors": [a.get("name") for a in p.get("authors", [])][:6],
            "year": year,
            "abstract": (p.get("abstract") or "")[:500] or None,
            "url": p.get("url"),
            "pdf": (p.get("openAccessPdf") or {}).get("url"),
            "doi": (p.get("externalIds") or {}).get("DOI")})
    return out


SOURCES = {"pubmed": search_pubmed, "arxiv": search_arxiv, "s2": search_s2}


def norm_title(t: str | None) -> str:
    return re.sub(r"\W+", "", (t or "").lower())


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("query", nargs="+")
    p.add_argument("--source", choices=[*SOURCES, "all"], default="all")
    p.add_argument("--max", type=int, default=10)
    p.add_argument("--year-min", type=int)
    args = p.parse_args()
    query = " ".join(args.query)

    names = list(SOURCES) if args.source == "all" else [args.source]
    results, errors = [], {}
    for name in names:
        try:
            results.extend(SOURCES[name](query, args.max, args.year_min))
        except Exception as exc:
            errors[name] = str(exc)
            if args.source != "all":
                agentlib.die(f"{name} search failed: {exc}", 1)

    seen, deduped = set(), []
    for r in results:
        key = norm_title(r["title"]) or f"{r['source']}:{r['id']}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    out = {"query": query, "sources": names, "count": len(deduped),
           "results": deduped[:args.max]}
    if errors:
        out["errors"] = errors
    agentlib.emit(out)
    return 0 if deduped else 1


if __name__ == "__main__":
    sys.exit(main())
