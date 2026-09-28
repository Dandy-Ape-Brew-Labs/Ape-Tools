"""Structural code map: top-level definitions per file, or a budgeted
repo map. A cheap tree-sitter-free approximation (ripgrep patterns per
language) — a map for orientation, not a parser.

  code_map.py src/                        # definitions of all files under src/
  code_map.py src/app.py                  # one file
  code_map.py . --map --budget 4000       # repo map, ~4000 token cap
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

# Top-level definition patterns per extension.
PATTERNS = {
    ".py": r"^(?:async\s+)?(?:def|class)\s+\w+|^\w+\s*=\s*(?:lambda|partial)",
    ".js": r"^(?:export\s+)?(?:async\s+)?(?:function|class|const\s+\w+\s*=|let\s+\w+\s*=)",
    ".mjs": r"^(?:export\s+)?(?:async\s+)?(?:function|class|const\s+\w+\s*=)",
    ".ts": r"^(?:export\s+)?(?:async\s+)?(?:function|class|interface|type|enum|const\s+\w+\s*=)",
    ".tsx": r"^(?:export\s+)?(?:async\s+)?(?:function|class|interface|type|enum|const\s+\w+\s*=)",
    ".jsx": r"^(?:export\s+)?(?:async\s+)?(?:function|class|const\s+\w+\s*=)",
    ".go": r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?\w+|^type\s+\w+",
    ".rs": r"^(?:pub\s+)?(?:async\s+)?(?:fn|struct|enum|impl|trait|mod)\s+\w+",
    ".java": r"^(?:public|private|protected|static|final|abstract|\s)*\s*(?:class|interface|enum|record)\s+\w+",
    ".kt": r"^\s*(?:fun|class|object|interface)\s+\w+",
    ".c": r"^\w[\w\s\*]*\s+\w+\s*\([^;]*$|^typedef\s+",
    ".h": r"^\w[\w\s\*]*\s+\w+\s*\([^;]*$|^typedef\s+|^struct\s+\w+",
    ".cpp": r"^\w[\w\s:<>\*]*\s+\w+\s*\([^;]*$|^class\s+\w+|^struct\s+\w+",
    ".rb": r"^\s*(?:def|class|module)\s+\w+",
    ".sh": r"^\s*(?:function\s+)?\w+\s*\(\)\s*\{",
    ".lua": r"^\s*(?:local\s+)?function\s+[\w.:]+",
    ".swift": r"^\s*(?:func|class|struct|enum|protocol|extension)\s+\w+",
}


def defs_for(path: Path) -> list[dict]:
    pat = PATTERNS.get(path.suffix.lower())
    if not pat:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rx = re.compile(pat)
    out = []
    for i, line in enumerate(lines, 1):
        if rx.search(line):
            out.append({"line": i, "text": line.strip()[:120]})
    return out


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("path", help="file or directory")
    p.add_argument("--map", action="store_true",
                   help="repo-map mode: all files, budgeted")
    p.add_argument("--budget", type=int, default=8000,
                   help="approx. token cap for --map output")
    args = p.parse_args()

    root = Path(args.path)
    if root.is_file():
        agentlib.emit({str(root): defs_for(root)})
        return 0
    if not root.is_dir():
        agentlib.die(f"not found: {args.path}", 2)

    files = agentlib.iter_files(
        root, includes=["*" + e for e in PATTERNS], respect_gitignore=True)
    result = {}
    budget_chars = args.budget * 4
    used = 0
    for f in sorted(files):
        defs = defs_for(f)
        if not defs:
            continue
        rel = str(f.relative_to(root))
        if args.map:
            block = rel + ":\n" + "\n".join(f"  {d['line']}: {d['text']}" for d in defs)
            if used + len(block) > budget_chars:
                print(f"[map truncated at ~{args.budget} tokens]", file=sys.stderr)
                break
            used += len(block)
            print(block)
        else:
            result[rel] = defs
    if not args.map:
        agentlib.emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
