"""Find files by glob pattern, sorted by mtime (newest first).

  fs_glob.py "**/*.test.ts"
  fs_glob.py "config.*" --path src --max 20

Respects .gitignore and prunes build dirs unless --no-gitignore/--all.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("pattern", help="glob pattern, e.g. '**/*.py'")
    p.add_argument("--path", default=".", help="search root (default .)")
    p.add_argument("--max", type=int, default=200, help="result cap")
    p.add_argument("--no-gitignore", action="store_true")
    args = p.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        agentlib.die(f"not a directory: {args.path}", 2)

    files = agentlib.iter_files(
        root, includes=[args.pattern],
        respect_gitignore=not args.no_gitignore)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    capped = len(files) > args.max
    files = files[: args.max]

    agentlib.emit({
        "root": str(root), "pattern": args.pattern,
        "count": len(files), "capped": capped,
        "paths": [str(f) for f in files],
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
