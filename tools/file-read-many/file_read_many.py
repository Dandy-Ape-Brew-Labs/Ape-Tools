"""Batch-read many files matching glob patterns.

Concatenates files with `--- {path} ---` separators. A bare directory path
matches nothing — use globs. Respects .gitignore and prunes common build
dirs.

Examples:
  file_read_many.py --include "docs/*.md"
  file_read_many.py --root src --include "*.py" --exclude "*_test.py"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

SEPARATOR = "--- {path} ---"


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("paths", nargs="*", help="files or glob patterns")
    p.add_argument("--root", default=".", help="root dir for globs (default .)")
    p.add_argument("--include", action="append", help="glob to include (repeatable)")
    p.add_argument("--exclude", action="append", help="glob to exclude (repeatable)")
    p.add_argument("--no-gitignore", action="store_true")
    p.add_argument("--max-bytes", type=int, default=agentlib.MAX_READ_BYTES)
    p.add_argument("--no-numbers", action="store_true")
    args = p.parse_args()

    includes = list(args.include or [])
    includes += [a for a in args.paths if any(c in a for c in "*?[")]
    plain = [Path(a) for a in args.paths if not any(c in a for c in "*?[")]
    for path in plain:
        if path.is_dir():
            print(f"warn: '{path}' is a directory — pass a glob instead", file=sys.stderr)
        elif not path.exists():
            print(f"warn: '{path}' not found, skipped", file=sys.stderr)

    matched = set(p.resolve() for p in plain if p.is_file())
    if includes:
        matched |= {
            f.resolve() for f in agentlib.iter_files(
                args.root, includes, args.exclude,
                respect_gitignore=not args.no_gitignore)
        }
    if not matched:
        agentlib.die("no files matched (a bare directory matches nothing — use a glob)", 2)

    out_parts, total_bytes, skipped = [], 0, 0
    for path in sorted(matched):
        if agentlib.is_binary(path):
            skipped += 1
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"warn: {path}: {exc}", file=sys.stderr)
            continue
        if not args.no_numbers:
            lines = text.splitlines()
            width = len(str(len(lines)))
            text = "\n".join(f"{i+1}\t{l}" for i, l in enumerate(lines))
        block = SEPARATOR.format(path=path) + "\n" + text
        out_parts.append(block)
        total_bytes += len(block.encode())

    body = "\n".join(out_parts)
    body, truncated = agentlib.truncate_text(body, args.max_bytes)
    print(body)
    if skipped:
        print(f"[skipped {skipped} binary files]", file=sys.stderr)
    if truncated:
        print(f"[truncated at {args.max_bytes} bytes; narrow your globs]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
