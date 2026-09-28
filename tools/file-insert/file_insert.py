"""Insert text after a given line — append/insert without a unique anchor.

  file_insert.py app.py --line 12 --text "import os"
  file_insert.py app.py --line 0 --text "# header"     # top of file
  echo "EOF marker" | file_insert.py app.py --line -1  # end of file
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("path")
    p.add_argument("--line", type=int, required=True,
                   help="insert AFTER this line; 0 = top, -1 = end of file")
    p.add_argument("--text", help="text to insert (or stdin)")
    args = p.parse_args()

    text = args.text if args.text is not None else sys.stdin.read()
    path = Path(args.path)
    if not path.is_file():
        agentlib.die(f"not a file: {path}", 2)

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    n = len(lines)
    insert_after = n if args.line == -1 else args.line
    if not 0 <= insert_after <= n:
        agentlib.die(f"--line {args.line} out of range (file has {n} lines)", 2)

    if text and not text.endswith("\n"):
        text += "\n"
    new_lines = lines[:insert_after] + [text] + lines[insert_after:]
    path.write_text("".join(new_lines), encoding="utf-8")

    agentlib.emit({
        "path": str(path.resolve()),
        "inserted_after_line": insert_after,
        "inserted_lines": text.count("\n"),
        "total_lines": n + text.count("\n"),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
