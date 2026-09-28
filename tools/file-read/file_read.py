"""Read a text file with line numbers, ranges, head/tail and size caps.

Locate first (grep/glob), then read a range — don't read huge files whole.

Examples:
  file_read.py src/app.py                     # whole file (capped)
  file_read.py src/app.py --offset 120 --limit 60     # lines 120-179
  file_read.py src/app.py --start 120 --end 180       # lines 120-180
  file_read.py app.log --tail 100
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def parse_args():
    p = agentlib.arg_parser(__doc__)
    p.add_argument("path")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--offset", type=int, help="1-based start line")
    g.add_argument("--start", type=int, help="1-based start line (inclusive)")
    g.add_argument("--head", type=int, help="first N lines")
    g.add_argument("--tail", type=int, help="last N lines")
    p.add_argument("--end", type=int, help="1-based end line (inclusive; -1 = EOF)")
    p.add_argument("--limit", type=int, help="line count (with --offset/--start)")
    p.add_argument("--max-lines", type=int, default=agentlib.MAX_READ_LINES,
                   help=f"output cap in lines (default {agentlib.MAX_READ_LINES})")
    p.add_argument("--no-numbers", action="store_true", help="omit line numbers")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.path)
    if not path.exists():
        agentlib.die(f"not found: {path}", 2)
    if path.is_dir():
        agentlib.die(f"'{path}' is a directory — use fs-list", 2)
    if agentlib.is_binary(path):
        agentlib.die(
            f"'{path}' looks binary ({agentlib.guess_mime(path)}); "
            "use file-media for images/PDFs or 'file' via run-shell", 2)

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        agentlib.die(f"cannot read {path}: {exc}")

    lines = text.splitlines()
    total = len(lines)

    if args.head is not None:
        start, end = 1, min(args.head, total)
    elif args.tail is not None:
        start, end = max(1, total - args.tail + 1), total
    else:
        start = args.offset or args.start or 1
        end = args.end if args.end is not None and args.end != -1 else None
        if args.limit is not None:
            end = start + args.limit - 1
        end = end if end is not None else total
        if start < 1:
            agentlib.die("--start/--offset must be >= 1", 2)
        if start > total and total:
            agentlib.die(f"start line {start} beyond EOF ({total} lines)", 2)
        end = min(end, total)

    view = lines[start - 1:end]
    truncated = False
    if len(view) > args.max_lines:
        view = view[: args.max_lines]
        truncated = True
    body = "\n".join(view)
    body, byte_trunc = agentlib.truncate_text(body)

    if args.no_numbers:
        numbered = body
    else:
        width = len(str(end))
        numbered = "\n".join(
            f"{start + i}\t{line}" for i, line in enumerate(body.split("\n"))
        ) if body else ""

    print(numbered)
    if truncated or byte_trunc or end < total:
        print(
            f"\n[showing lines {start}-{min(start + len(view) - 1, end)} of {total}; "
            "read more with --offset/--limit]",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
