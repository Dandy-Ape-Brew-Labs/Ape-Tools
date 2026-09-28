"""Query log files and systemd journal — grep + time-window + tail,
JSON or raw lines. Built for 'why is this thing broken' triage.

  logs_query.py file <path> [--grep PAT] [--since ISO] [--tail N]
                            [--level ERROR] [-C 3]
  logs_query.py journal [--unit NAME] [--since "1h ago"] [--grep PAT]
                        [--priority err] [-n 100]

--grep is a Python regex; --level matches ERROR/WARN/INFO/DEBUG text.
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

LEVELS = ("EMERG", "ALERT", "CRIT", "ERROR", "WARN", "NOTICE",
          "INFO", "DEBUG", "TRACE")


def since_arg(val: str) -> str:
    """Accept ISO or relative 'Nh/Nm/Nd ago' shorthand."""
    if re.fullmatch(r"\d+[smhd]\s*ago", val):
        return val
    return val


def parse_ts(line: str) -> datetime | None:
    """Try ISO timestamps at line start."""
    m = re.match(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", line)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1)).replace(
            tzinfo=timezone.utc) if m.group(1).find("T") >= 0 else \
            datetime.fromisoformat(m.group(1)).astimezone()
    except ValueError:
        return None


def filter_lines(lines: list[str], grep: str | None,
                 level: str | None, since: str | None,
                 context: int) -> list[str]:
    pat = re.compile(grep) if grep else None
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            else:
                since_dt = since_dt.astimezone(timezone.utc)
        except ValueError:
            agentlib.die(f"--since must be ISO for file mode: {since}", 2)
    lv_idx = LEVELS.index(level) if level else None
    keep = set()
    for i, ln in enumerate(lines):
        ok = True
        if pat and not pat.search(ln):
            ok = False
        if ok and lv_idx is not None:
            hit = next((j for j, lv in enumerate(LEVELS)
                        if lv in ln.upper()), None)
            ok = hit is not None and hit <= lv_idx
        if ok and since_dt:
            ts = parse_ts(ln)
            ok = ts is None or ts >= since_dt
        if ok:
            keep.update(range(max(0, i - context),
                              min(len(lines), i + context + 1)))
    return [lines[i] for i in sorted(keep)]


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="src", required=True)

    f = sub.add_parser("file"); f.add_argument("path")
    j = sub.add_parser("journal")
    j.add_argument("--unit"); j.add_argument("--priority",
        choices=[l.lower() for l in LEVELS[:7]])

    for s in (f, j):
        s.add_argument("--grep")
        s.add_argument("--since")
        s.add_argument("--tail", "-n", type=int)
    f.add_argument("--level", choices=LEVELS)
    f.add_argument("-C", "--context", type=int, default=0)
    j.add_argument("--user", action="store_true")
    args = p.parse_args()

    if args.src == "file":
        path = Path(args.path)
        if not path.is_file():
            agentlib.die(f"not a file: {args.path}", 2)
        lines = path.read_text(encoding="utf-8", errors="replace") \
                   .splitlines()
        out = filter_lines(lines, args.grep, args.level, args.since,
                           args.context)
        if args.tail:
            out = out[-args.tail:]
        agentlib.emit({"file": args.path, "matched": len(out),
                       "lines": out})
        return 0

    # journal
    g = ["journalctl", "--no-pager", "-o", "short-iso",
         "-n", str(args.tail or 100)]
    if args.user:
        g.append("--user")
    if args.unit:
        g += ["-u", args.unit]
    if args.priority:
        g += ["-p", args.priority]
    if args.since:
        g += ["--since", since_arg(args.since)]
    if args.grep:
        g += ["--grep", args.grep]
    r = subprocess.run(g, capture_output=True, text=True)
    if r.returncode != 0:
        agentlib.die(r.stderr.strip(), 1)
    lines = r.stdout.splitlines()
    agentlib.emit({"source": "journal", "unit": args.unit,
                   "lines": lines})
    return 0


if __name__ == "__main__":
    sys.exit(main())
