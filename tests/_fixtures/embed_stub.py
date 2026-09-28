"""Deterministic OpenAI-compatible embedding stub for smoke tests.

Usage: embed_stub.py <portfile>
Binds 127.0.0.1:0, writes the chosen port to <portfile>, serves:
  GET  /v1/models      -> {"data":[{"id":"stub-embed"}]}
  POST /v1/embeddings  -> bag-of-words vectors (token md5 -> dim)
"""

import hashlib
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIM = 64


def vec(text: str) -> list[float]:
    v = [0.0] * DIM
    for tok in re.findall(r"\w+", text.lower()):
        h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "little")
        v[h % DIM] += 1.0
    return v


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self._json({"data": [{"id": "stub-embed"}]})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/v1/embeddings":
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n))
            inp = req.get("input", [])
            if isinstance(inp, str):
                inp = [inp]
            self._json({"data": [{"index": i, "embedding": vec(t)}
                                 for i, t in enumerate(inp)]})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
with open(sys.argv[1], "w") as fh:
    fh.write(str(server.server_address[1]))
server.serve_forever()
