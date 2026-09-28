"""RAG over local document stores — index docs, retrieve chunks with
source citations. Named stores live under $AGENT_TOOLS_HOME/knowledge/.

  knowledge.py add <name> <path>            # index file/dir into store
  knowledge.py query <text> [--store name|*] [--k 6]
  knowledge.py list
  knowledge.py remove <name>
  knowledge.py stats <name>

Formats: .md/.markdown/.rst/.txt read directly, .html tag-stripped,
.pdf via pdftotext when installed (skipped otherwise).
Embeddings via $LLM_BASE_URL/v1/embeddings — same convention as
semantic-search. Model: $AGENT_EMBED_MODEL or auto-detect.
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
from array import array
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

DOC_EXT = {".md", ".markdown", ".rst", ".txt", ".html", ".htm", ".pdf"}
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 200
BATCH = 32


def base_url() -> str:
    return os.environ.get(
        "LLM_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")


def http_json(url: str, body: dict | None = None, timeout: int = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception as exc:
        agentlib.die(
            f"embedding endpoint unreachable at {base_url()} — start "
            f"LM Studio or set LLM_BASE_URL ({exc})", 3)


def embed_model(base: str) -> str:
    model = os.environ.get("AGENT_EMBED_MODEL")
    if model:
        return model
    ids = [m.get("id", "")
           for m in http_json(f"{base}/models").get("data", [])]
    for i in ids:
        if "embed" in i.lower():
            return i
    if ids:
        return ids[0]
    agentlib.die(f"no models on {base}", 3)


def embed(texts: list[str], model: str, base: str) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        data = http_json(f"{base}/embeddings",
                         {"model": model, "input": texts[i:i + BATCH]},
                         timeout=180)
        ordered = sorted(data["data"], key=lambda d: d.get("index", 0))
        out.extend(d["embedding"] for d in ordered)
    return out


class Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def extract(path: Path) -> str | None:
    ext = path.suffix.lower()
    try:
        if ext in (".md", ".markdown", ".rst", ".txt"):
            return path.read_text(encoding="utf-8", errors="replace")
        if ext in (".html", ".htm"):
            s = Stripper()
            s.feed(path.read_text(encoding="utf-8", errors="replace"))
            return " ".join(s.parts)
        if ext == ".pdf":
            if not agentlib.which("pdftotext"):
                print(f"warn: pdftotext missing, skipping {path}",
                      file=sys.stderr)
                return None
            r = agentlib.run_cmd(["pdftotext", str(path), "-"], timeout=30)
            return r["stdout"] or None
    except OSError:
        return None
    return None


def chunk_document(text: str) -> list[tuple[str, str]]:
    """Split on markdown headings, window to ~CHUNK_CHARS with overlap.

    Returns [(heading, text)]."""
    sections: list[tuple[str, str]] = []
    heading, buf = "", []
    for line in text.splitlines():
        m = re.match(r"^#{1,4}\s+(.*)", line)
        if m:
            if buf:
                sections.append((heading, "\n".join(buf)))
            heading, buf = m.group(1).strip(), [line]
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf)))
    if not sections:
        sections = [("", text)]

    out: list[tuple[str, str]] = []
    for head, sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if len(sec) <= CHUNK_CHARS:
            out.append((head, sec))
            continue
        step = CHUNK_CHARS - CHUNK_OVERLAP
        for i in range(0, len(sec), step):
            out.append((head, sec[i:i + CHUNK_CHARS]))
            if i + CHUNK_CHARS >= len(sec):
                break
    return out


def store_path(name: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        agentlib.die(f"bad store name '{name}' — use [a-zA-Z0-9_-]", 2)
    return agentlib.state_dir("knowledge") / f"{name}.sqlite"


def open_store(path: Path) -> sqlite3.Connection:
    cx = sqlite3.connect(path)
    cx.execute("CREATE TABLE IF NOT EXISTS files("
               "path TEXT PRIMARY KEY, hash TEXT, indexed REAL)")
    cx.execute("CREATE TABLE IF NOT EXISTS chunks("
               "path TEXT, heading TEXT, text TEXT, emb BLOB)")
    return cx


def pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def unpack(blob: bytes) -> array:
    return array("f", blob)


def cmd_add(args) -> int:
    root = Path(args.path).resolve()
    if not root.exists():
        agentlib.die(f"not found: {root}", 2)
    base = base_url()
    model = embed_model(base)
    cx = open_store(store_path(args.name))
    if root.is_dir():
        files = agentlib.iter_files(
            root, includes=[f"*{e}" for e in DOC_EXT])
    else:
        files = [root]
    indexed, skipped = 0, 0
    for f in files:
        text = extract(f)
        if not text or not text.strip():
            continue
        digest = hashlib.sha256(text.encode()).hexdigest()
        rel = str(f)
        row = cx.execute("SELECT hash FROM files WHERE path=?",
                         (rel,)).fetchone()
        if row and row[0] == digest:
            skipped += 1
            continue
        chunks = chunk_document(text)
        vecs = embed([t for _, t in chunks], model, base)
        cx.execute("DELETE FROM chunks WHERE path=?", (rel,))
        cx.executemany(
            "INSERT INTO chunks(path,heading,text,emb) VALUES(?,?,?,?)",
            [(rel, h, t, pack(v)) for (h, t), v in zip(chunks, vecs)])
        cx.execute("INSERT OR REPLACE INTO files VALUES(?,?,?)",
                   (rel, digest, time.time()))
        indexed += 1
    cx.commit()
    agentlib.emit({"store": args.name, "indexed": indexed,
                   "skipped_unchanged": skipped, "model": model})
    return 0


def cmd_query(args) -> int:
    base = base_url()
    model = embed_model(base)
    qv = embed([args.text], model, base)[0]
    nq = sum(x * x for x in qv) ** 0.5 or 1.0
    kdir = agentlib.state_dir("knowledge")
    stores = ([args.store] if args.store != "*"
              else sorted(p.stem for p in kdir.glob("*.sqlite")))
    hits = []
    for name in stores:
        sp = kdir / f"{name}.sqlite"
        if not sp.exists():
            continue
        cx = open_store(sp)
        for path, heading, text, blob in cx.execute(
                "SELECT path,heading,text,emb FROM chunks"):
            v = unpack(blob)
            nv = sum(x * x for x in v) ** 0.5 or 1.0
            score = sum(a * b for a, b in zip(qv, v)) / (nq * nv)
            hits.append((score, name, path, heading, text))
        cx.close()
    hits.sort(key=lambda h: -h[0])
    out = [{"store": n, "source": p, "heading": h or None,
            "score": round(sc, 4), "text": " ".join(t.split())[:400]}
           for sc, n, p, h, t in hits[:args.k]]
    agentlib.emit({"query": args.text, "model": model,
                   "count": len(out), "results": out})
    return 0 if out else 1


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("name"); a.add_argument("path")
    q = sub.add_parser("query"); q.add_argument("text", nargs="+")
    q.add_argument("--store", default="*")
    q.add_argument("--k", type=int, default=6)
    sub.add_parser("list")
    r = sub.add_parser("remove"); r.add_argument("name")
    s = sub.add_parser("stats"); s.add_argument("name")
    args = p.parse_args()

    if args.cmd == "add":
        return cmd_add(args)
    if args.cmd == "query":
        args.text = " ".join(args.text)
        return cmd_query(args)
    if args.cmd == "list":
        kdir = agentlib.state_dir("knowledge")
        out = []
        for sp in sorted(kdir.glob("*.sqlite")):
            cx = open_store(sp)
            out.append({"store": sp.stem,
                        "files": cx.execute(
                            "SELECT COUNT(*) FROM files").fetchone()[0],
                        "chunks": cx.execute(
                            "SELECT COUNT(*) FROM chunks").fetchone()[0],
                        "db_bytes": sp.stat().st_size})
            cx.close()
        agentlib.emit(out)
        return 0
    if args.cmd == "remove":
        sp = store_path(args.name)
        if not sp.exists():
            agentlib.die(f"no store '{args.name}'", 2)
        sp.unlink()
        agentlib.emit({"removed": args.name})
        return 0
    if args.cmd == "stats":
        sp = store_path(args.name)
        if not sp.exists():
            agentlib.die(f"no store '{args.name}'", 2)
        cx = open_store(sp)
        agentlib.emit({
            "store": args.name,
            "files": cx.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "chunks": cx.execute(
                "SELECT COUNT(*) FROM chunks").fetchone()[0],
            "db_bytes": sp.stat().st_size})
        return 0


if __name__ == "__main__":
    sys.exit(main())
