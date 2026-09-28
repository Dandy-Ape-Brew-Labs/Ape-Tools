"""Intent-based search over the tool catalogue.

BM25-lite scoring over name + use_when + description + keywords + args.
Use this to find the right tool before loading its full manifest.

Usage:
  tool-search <query...>          # ranked results (top 5) with full manifests
  tool-search --select a,b        # exact manifest lookup by name
"""

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

TOOLS_DIR = Path(__file__).resolve().parent.parent
STOP = {"a", "an", "the", "and", "or", "of", "to", "in", "for", "on", "with", "is", "it"}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9_]+", text.lower()) if t not in STOP]


def doc_text(m: dict) -> str:
    parts = [
        m.get("name", "").replace("-", " "),
        m.get("name", "").replace("-", " "),  # name weighted x2
        m.get("use_when", "") or "",
        m.get("use_when", "") or "",          # use_when weighted x2
        m.get("description", ""),
        " ".join(m.get("keywords", [])),
        " ".join(m.get("keywords", [])),
        m.get("category", ""),
    ]
    for arg in m.get("args", []):
        parts.append(arg.get("name", "").lstrip("-").replace("-", " "))
        parts.append(arg.get("description", ""))
    return " ".join(parts)


def load_manifests() -> list[dict]:
    manifests = []
    for p in sorted(TOOLS_DIR.glob("*/tool.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            m["dir"] = p.parent.name
            manifests.append(m)
        except json.JSONDecodeError:
            print(f"warn: {p}: invalid JSON, skipped", file=sys.stderr)
    return manifests


def bm25(query_terms: list[str], docs: list[list[str]], k1=1.5, b=0.75) -> list[float]:
    avg_len = sum(len(d) for d in docs) / max(len(docs), 1)
    df: Counter = Counter()
    tfs = []
    for d in docs:
        tf = Counter(d)
        tfs.append(tf)
        for term in tf:
            df[term] += 1
    n = len(docs)
    scores = []
    for tf in tfs:
        score = 0.0
        for term in query_terms:
            f = tf.get(term, 0)
            if f == 0:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * len(tf) / avg_len))
        scores.append(score)
    return scores


def main() -> int:
    parser = agentlib.arg_parser(__doc__)
    parser.add_argument("query", nargs="*", help="search terms (intent)")
    parser.add_argument("--select", help="comma-separated tool names for exact lookup")
    parser.add_argument("--max", type=int, default=5, help="max results (default 5)")
    parser.add_argument(
        "--names-only",
        action="store_true",
        help="print ranked names + scores only, no full manifests",
    )
    args = parser.parse_args()

    manifests = load_manifests()
    if not manifests:
        agentlib.die("no tool manifests found under tools/")

    if args.select:
        wanted = {n.strip() for n in args.select.split(",")}
        found = [m for m in manifests if m["name"] in wanted or m["dir"] in wanted]
        missing = wanted - {m["name"] for m in found} - {m["dir"] for m in found}
        for name in missing:
            print(f"warn: no tool named '{name}'", file=sys.stderr)
        agentlib.emit(found)
        return 0 if found else 1

    if not args.query:
        agentlib.die("provide a query or --select names", 2)

    query_terms = tokenize(" ".join(args.query))
    docs = [tokenize(doc_text(m)) for m in manifests]
    scores = bm25(query_terms, docs)
    ranked = sorted(zip(scores, manifests), key=lambda t: t[0], reverse=True)
    ranked = [r for r in ranked if r[0] > 0][: args.max]

    if not ranked:
        print("no tools matched; broaden the query or check list-tools --index", file=sys.stderr)
        return 1

    if args.names_only:
        for score, m in ranked:
            print(f"{score:6.2f}  {m['name']} — {m.get('use_when', '')}")
        return 0

    agentlib.emit([m for _, m in ranked])
    return 0


if __name__ == "__main__":
    sys.exit(main())
