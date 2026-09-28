"""Content search via ripgrep. Scope every search — unscoped regex over a
monorepo floods context.

Modes:
  --mode files    which files match (default with a pattern over a dir)
  --mode content  matching lines with context
  --mode count    match counts per file

Examples:
  code_grep.py "def\\s+parse_" --type py --mode content
  code_grep.py "TODO" --path src --mode files
  code_grep.py "interface\\{" --glob "*.ts" -C 3
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("pattern", help="regex (ripgrep syntax; no lookaround)")
    p.add_argument("--path", default=".", help="search root")
    p.add_argument("--glob", action="append", help="file glob, e.g. '*.py'")
    p.add_argument("--type", help="ripgrep file type (py, js, rust, ...)")
    p.add_argument("-i", "--ignore-case", action="store_true")
    p.add_argument("-C", "--context", type=int, default=0)
    p.add_argument("-A", type=int, default=0)
    p.add_argument("-B", type=int, default=0)
    p.add_argument("--mode", choices=["files", "content", "count"],
                   default="content")
    p.add_argument("--max", type=int, default=100, help="result cap")
    p.add_argument("--offset", type=int, default=0, help="pagination offset")
    args = p.parse_args()

    rg = agentlib.require_bin(
        "rg", "Install ripgrep: https://github.com/BurntSushi/ripgrep")

    argv = [rg, "--json", "--line-number", "--column",
            "-e", args.pattern, args.path]
    if args.ignore_case:
        argv.append("-i")
    if args.type:
        argv += ["--type", args.type]
    for g in args.glob or []:
        argv += ["--glob", g]
    ctx = max(args.context, args.A, args.B)
    if args.A:
        argv += ["-A", str(args.A)]
    if args.B:
        argv += ["-B", str(args.B)]
    elif ctx:
        argv += ["-C", str(ctx)]

    res = agentlib.run_cmd(argv)
    if res["exit"] not in (0, 1):  # rg: 1 = no matches
        agentlib.die(f"rg failed: {res['stderr'].strip()}")

    matches = []       # {path, line, col, text, kind}
    for raw in res["stdout"].splitlines():
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if ev["type"] == "match":
            d = ev["data"]
            matches.append({
                "path": d["path"]["text"],
                "line": d["line_number"],
                "col": d.get("submatches", [{}])[0].get("start", 0) + 1,
                "text": d["lines"]["text"].rstrip("\n"),
            })
        elif ev["type"] == "context":
            d = ev["data"]
            matches.append({
                "path": d["path"]["text"], "line": d["line_number"],
                "text": d["lines"]["text"].rstrip("\n"), "context": True,
            })

    if args.mode == "files":
        seen = list(dict.fromkeys(m["path"] for m in matches if not m.get("context")))
        agentlib.emit({"count": len(seen), "files": seen[: args.max],
                       "truncated": len(seen) > args.max})
        return 0
    if args.mode == "count":
        counts = {}
        for m in matches:
            if not m.get("context"):
                counts[m["path"]] = counts.get(m["path"], 0) + 1
        agentlib.emit({"counts": counts})
        return 0

    total = len(matches)
    page = matches[args.offset: args.offset + args.max]
    agentlib.emit({
        "total": total, "shown": len(page), "offset": args.offset,
        "truncated": args.offset + len(page) < total,
        "matches": page,
        "hint": "paginate with --offset" if args.offset + len(page) < total else None,
    })
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
