"""Semantic code search over a local embedding index.

  semantic_search.py index <path>           # build/update index (incremental)
  semantic_search.py query <text> [--k 8] [--path substr]
  semantic_search.py stats
  semantic_search.py clear

Embeddings come from $LLM_BASE_URL/v1/embeddings (LM Studio or any
OpenAI-compatible endpoint). Model: $AGENT_EMBED_MODEL, else auto-detect
(first 'embed' model on the endpoint). Index lives at
$AGENT_TOOLS_HOME/semantic/code.sqlite. The endpoint is required for
indexing and querying (queries embed too).
"""

import ast
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.request
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".go", ".rs",
    ".java", ".c", ".h", ".cpp", ".cc", ".hpp", ".cs", ".rb", ".php",
    ".sh", ".bash", ".sql", ".md", ".txt", ".rst", ".yaml", ".yml",
    ".toml",
}
MAX_FILE_BYTES = 512 * 1024
BLOCK_LINES = 100
BLOCK_OVERLAP = 15
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


def chunk_python(text: str) -> list[tuple[int, int, str]]:
    """Top-level def/class chunks plus a preamble chunk."""
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return chunk_lines(lines)
    spans = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and node.end_lineno:
            spans.append((node.lineno, node.end_lineno))
    chunks = []
    first = min((s for s, _ in spans), default=len(lines) + 1)
    if first > 6:
        chunks.append((1, first - 1, "\n".join(lines[:first - 1])))
    for start, end in spans:
        chunks.append((start, end, "\n".join(lines[start - 1:end])))
    # split oversized chunks
    out = []
    for s, e, t in chunks:
        if e - s > BLOCK_LINES:
            out.extend(chunk_lines(t.splitlines(), base=s))
        else:
            out.append((s, e, t))
    return out


def chunk_lines(lines: list[str], base: int = 1) -> list[tuple[int, int, str]]:
    out = []
    step = BLOCK_LINES - BLOCK_OVERLAP
    for i in range(0, len(lines), step):
        seg = lines[i:i + BLOCK_LINES]
        if not any(l.strip() for l in seg):
            continue
        out.append((base + i, base + i + len(seg) - 1, "\n".join(seg)))
        if i + BLOCK_LINES >= len(lines):
            break
    return out


def chunk_file(path: Path, text: str) -> list[tuple[int, int, str]]:
    if path.suffix.lower() == ".py":
        return chunk_python(text)
    return chunk_lines(text.splitlines())


def db() -> sqlite3.Connection:
    path = agentlib.state_dir("semantic") / "code.sqlite"
    cx = sqlite3.connect(path)
    cx.execute("CREATE TABLE IF NOT EXISTS files("
               "path TEXT PRIMARY KEY, hash TEXT, indexed REAL)")
    cx.execute("CREATE TABLE IF NOT EXISTS chunks("
               "path TEXT, start INT, end INT, text TEXT, emb BLOB)")
    cx.execute("CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path)")
    return cx


def pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def unpack(blob: bytes) -> array:
    return array("f", blob)


def cmd_index(args) -> int:
    root = Path(args.path).resolve()
    if not root.is_dir():
        agentlib.die(f"not a directory: {root}", 2)
    base = base_url()
    model = embed_model(base)
    cx = db()
    files = agentlib.iter_files(
        root, includes=[f"*{e}" for e in CODE_EXT])
    seen, indexed, skipped = set(), 0, 0
    for f in files:
        rel = str(f)
        seen.add(rel)
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        if len(raw) > MAX_FILE_BYTES or agentlib.is_binary(f):
            continue
        digest = hashlib.sha256(raw).hexdigest()
        row = cx.execute("SELECT hash FROM files WHERE path=?",
                         (rel,)).fetchone()
        if row and row[0] == digest:
            skipped += 1
            continue
        chunks = chunk_file(f, raw.decode("utf-8", errors="replace"))
        if not chunks:
            continue
        vecs = embed([t for _, _, t in chunks], model, base)
        cx.execute("DELETE FROM chunks WHERE path=?", (rel,))
        cx.executemany(
            "INSERT INTO chunks(path,start,end,text,emb) VALUES(?,?,?,?,?)",
            [(rel, s, e, t, pack(v)) for (s, e, t), v in zip(chunks, vecs)])
        cx.execute("INSERT OR REPLACE INTO files VALUES(?,?,?)",
                   (rel, digest, time.time()))
        indexed += 1
    # prune files that vanished from this root
    stale = [r[0] for r in cx.execute(
        "SELECT path FROM files WHERE path LIKE ?", (str(root) + "%",))
        if r[0] not in seen]
    for p in stale:
        cx.execute("DELETE FROM chunks WHERE path=?", (p,))
        cx.execute("DELETE FROM files WHERE path=?", (p,))
    cx.commit()
    agentlib.emit({"indexed": indexed, "skipped_unchanged": skipped,
                   "pruned": len(stale), "model": model})
    return 0


def cmd_query(args) -> int:
    base = base_url()
    model = embed_model(base)
    qv = embed([args.text], model, base)[0]
    nq = sum(x * x for x in qv) ** 0.5 or 1.0
    cx = db()
    like = f"%{args.path}%" if args.path else "%"
    hits = []
    for path, s, e, text, blob in cx.execute(
            "SELECT path,start,end,text,emb FROM chunks WHERE path LIKE ?",
            (like,)):
        v = unpack(blob)
        nv = sum(x * x for x in v) ** 0.5 or 1.0
        score = sum(a * b for a, b in zip(qv, v)) / (nq * nv)
        hits.append((score, path, s, e, text))
    hits.sort(key=lambda h: -h[0])
    out = [{"path": p, "start_line": s, "end_line": e,
            "score": round(sc, 4),
            "snippet": " ".join(t.split())[:160]}
           for sc, p, s, e, t in hits[:args.k]]
    agentlib.emit({"query": args.text, "model": model,
                   "count": len(out), "results": out})
    return 0 if out else 1


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("index"); i.add_argument("path")
    q = sub.add_parser("query"); q.add_argument("text", nargs="+")
    q.add_argument("--k", type=int, default=8)
    q.add_argument("--path", help="substring filter on indexed paths")
    sub.add_parser("stats")
    sub.add_parser("clear")
    args = p.parse_args()

    if args.cmd == "index":
        return cmd_index(args)
    if args.cmd == "query":
        args.text = " ".join(args.text)
        return cmd_query(args)
    if args.cmd == "stats":
        cx = db()
        n_files = cx.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        n_chunks = cx.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        db_path = agentlib.state_dir("semantic") / "code.sqlite"
        agentlib.emit({"files": n_files, "chunks": n_chunks,
                       "db": str(db_path),
                       "db_bytes": db_path.stat().st_size})
        return 0
    if args.cmd == "clear":
        cx = db()
        cx.execute("DELETE FROM chunks")
        cx.execute("DELETE FROM files")
        cx.commit()
        agentlib.emit({"cleared": True})
        return 0


if __name__ == "__main__":
    sys.exit(main())
