"""Write a file: create new or overwrite (with --force). Parents auto-created.

Content comes from --content or stdin. Overwriting an existing file requires
--force — the file's previous content is reported in the error so callers
know a read-first step is expected.

  file_write.py out.py --content "print('hi')"
  echo "data" | file_write.py out.txt -
  file_write.py existing.py --content "..." --force
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("path", help="file to write")
    p.add_argument("content", nargs="?", help="inline content, or '-' for stdin")
    p.add_argument("--content", dest="content_opt", help="content (same as positional)")
    p.add_argument("--force", action="store_true", help="overwrite existing file")
    p.add_argument("--append", action="store_true", help="append instead of overwrite")
    args = p.parse_args()

    content = args.content_opt if args.content_opt is not None else args.content
    if content == "-" or content is None:
        content = sys.stdin.read()
    if content is None:
        agentlib.die("no content provided (arg, --content, or stdin)", 2)

    path = Path(args.path)
    existed = path.exists()
    if existed and path.is_dir():
        agentlib.die(f"'{path}' is a directory", 2)
    if existed and not (args.force or args.append):
        st = path.stat()
        agentlib.die(
            f"'{path}' already exists ({st.st_size} bytes). Read it first with "
            "file-read, then overwrite with --force or edit in place with file-edit.", 2)

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if args.append:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(content)
        else:
            path.write_text(content, encoding="utf-8")
    except OSError as exc:
        agentlib.die(f"write failed: {exc}")

    agentlib.emit({
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "action": "appended" if args.append else ("overwritten" if existed else "created"),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
