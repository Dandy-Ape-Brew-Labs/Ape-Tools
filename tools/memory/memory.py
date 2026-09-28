"""Persistent memory store — markdown files under
$AGENT_TOOLS_HOME/memories/. Mirrors the Anthropic memory tool's
command vocabulary.

  memory.py list
  memory.py view notes.md [--range 5-10]
  memory.py create notes.md --text "user prefers uv"
  memory.py str_replace notes.md --old "x" --new "y"
  memory.py insert notes.md --line 3 --text "dated fact"
  memory.py delete notes.md
  memory.py rename notes.md prefs.md

Write concise, dated facts — not transcripts. Never store secrets.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def memories() -> Path:
    return agentlib.state_dir("memories")


def resolve(name: str) -> Path:
    p = (memories() / name).resolve()
    if not str(p).startswith(str(memories().resolve())):
        agentlib.die("name escapes memories dir", 2)
    return p


def body(args) -> str:
    return args.text if args.text is not None else sys.stdin.read()


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    v = sub.add_parser("view"); v.add_argument("name")
    v.add_argument("--range", help="line range e.g. 5-10")
    c = sub.add_parser("create"); c.add_argument("name")
    c.add_argument("--text", help="content or stdin")
    c.add_argument("--force", action="store_true", help="overwrite existing")
    r = sub.add_parser("str_replace"); r.add_argument("name")
    r.add_argument("--old", required=True); r.add_argument("--new", required=True)
    i = sub.add_parser("insert"); i.add_argument("name")
    i.add_argument("--line", type=int, required=True)
    i.add_argument("--text", help="content or stdin")
    d = sub.add_parser("delete"); d.add_argument("name")
    rn = sub.add_parser("rename"); rn.add_argument("old"); rn.add_argument("new")
    args = p.parse_args()

    if args.cmd == "list":
        files = sorted(memories().glob("**/*.md"))
        agentlib.emit([str(f.relative_to(memories())) for f in files])
        return 0

    if args.cmd == "view":
        path = resolve(args.name)
        if not path.is_file():
            agentlib.die(f"no memory '{args.name}'", 2)
        lines = path.read_text(encoding="utf-8").splitlines()
        if args.range:
            a, _, b = args.range.partition("-")
            lines = lines[int(a) - 1: int(b)]
        w = len(str(len(lines)))
        print("\n".join(f"{i+1}\t{l}" for i, l in enumerate(lines)))
        return 0

    if args.cmd == "create":
        path = resolve(args.name)
        if path.exists() and not args.force:
            agentlib.die(f"'{args.name}' exists (--force to overwrite)", 2)
        text = body(args)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        agentlib.emit({"created": args.name, "bytes": len(text.encode())})
        return 0

    if args.cmd == "str_replace":
        path = resolve(args.name)
        if not path.is_file():
            agentlib.die(f"no memory '{args.name}'", 2)
        text = path.read_text(encoding="utf-8")
        n = text.count(args.old)
        if n == 0:
            agentlib.die("old string not found — view the file first", 1)
        if n > 1:
            agentlib.die(f"old string matches {n} times — widen context", 1)
        path.write_text(text.replace(args.old, args.new, 1))
        agentlib.emit({"updated": args.name})
        return 0

    if args.cmd == "insert":
        path = resolve(args.name)
        if not path.is_file():
            agentlib.die(f"no memory '{args.name}'", 2)
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        text = body(args)
        if text and not text.endswith("\n"):
            text += "\n"
        at = max(0, min(args.line, len(lines)))
        path.write_text("".join(lines[:at] + [text] + lines[at:]))
        agentlib.emit({"updated": args.name, "inserted_after": at})
        return 0

    if args.cmd == "delete":
        path = resolve(args.name)
        if not path.is_file():
            agentlib.die(f"no memory '{args.name}'", 2)
        path.unlink()
        agentlib.emit({"deleted": args.name})
        return 0

    if args.cmd == "rename":
        old, new = resolve(args.old), resolve(args.new)
        if not old.is_file():
            agentlib.die(f"no memory '{args.old}'", 2)
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
        agentlib.emit({"renamed": args.old, "to": args.new})
        return 0


if __name__ == "__main__":
    sys.exit(main())
