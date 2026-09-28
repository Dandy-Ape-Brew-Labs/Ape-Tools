"""Deterministic utility operations agents need mid-task — hashing,
time, encoding, env inspection — so they don't shell out ad-hoc.

  util_kit.py now [--utc]
  util_kit.py hash <file> [--algo sha256]
  util_kit.py b64 <encode|decode> --text "..." | <file>
  util_kit.py env [--prefix AGENT_]
  util_kit.py uuid
  util_kit.py json <pretty|keys> [file]      # stdin if no file
"""

import base64
import hashlib
import json
import os
import sys
import uuid as uuidlib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("now"); n.add_argument("--utc", action="store_true")
    h = sub.add_parser("hash"); h.add_argument("file")
    h.add_argument("--algo", default="sha256",
                   choices=sorted(hashlib.algorithms_available))
    b = sub.add_parser("b64"); b.add_argument("op", choices=["encode", "decode"])
    b.add_argument("--text"); b.add_argument("--file")
    e = sub.add_parser("env"); e.add_argument("--prefix", default="")
    sub.add_parser("uuid")
    j = sub.add_parser("json"); j.add_argument("op", choices=["pretty", "keys"])
    j.add_argument("file", nargs="?")
    args = p.parse_args()

    if args.cmd == "now":
        dt = datetime.now(timezone.utc) if args.utc else datetime.now().astimezone()
        agentlib.emit({"iso": dt.isoformat(), "epoch": dt.timestamp(),
                       "tz": str(dt.tzinfo)})
        return 0

    if args.cmd == "hash":
        path = Path(args.file)
        if not path.is_file():
            agentlib.die(f"not a file: {args.file}", 2)
        digest = hashlib.new(args.algo)
        digest.update(path.read_bytes())
        agentlib.emit({"file": args.file, "algo": args.algo,
                       "hex": digest.hexdigest()})
        return 0

    if args.cmd == "b64":
        if args.file:
            raw = Path(args.file).read_bytes()
        elif args.text is not None:
            raw = args.text.encode()
        else:
            raw = sys.stdin.buffer.read()
        if args.op == "encode":
            print(base64.b64encode(raw).decode())
        else:
            try:
                sys.stdout.buffer.write(base64.b64decode(raw.strip()))
            except Exception:
                agentlib.die("invalid base64 input", 2)
        return 0

    if args.cmd == "env":
        items = {k: v for k, v in sorted(os.environ.items())
                 if k.startswith(args.prefix)}
        redacted = {k: ("***" if any(s in k.upper()
                    for s in ("KEY", "TOKEN", "SECRET", "PASSWORD")) else v)
                    for k, v in items.items()}
        agentlib.emit(redacted)
        return 0

    if args.cmd == "uuid":
        print(uuidlib.uuid4())
        return 0

    if args.cmd == "json":
        raw = Path(args.file).read_text() if args.file else sys.stdin.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            agentlib.die(f"invalid JSON: {exc}", 2)
        if args.op == "pretty":
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            if not isinstance(data, dict):
                agentlib.die("keys op requires a JSON object", 2)
            agentlib.emit(sorted(data.keys()))
        return 0


if __name__ == "__main__":
    sys.exit(main())
