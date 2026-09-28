"""List directory contents: one level, or a depth-limited tree.

  fs_list.py src                 # one level
  fs_list.py . --tree --depth 3  # orientation in an unknown repo
  fs_list.py . --all             # include hidden files

Always prunes .git, node_modules, .venv and friends. JSON output.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

MAX_ENTRIES = 500


def entry(path: Path) -> dict:
    e = {"name": path.name + ("/" if path.is_dir() else ""),
         "type": "dir" if path.is_dir() else "file"}
    if path.is_file():
        e["size"] = path.stat().st_size
    return e


def tree(root: Path, depth: int, show_hidden: bool, out: list, prefix=""):
    try:
        children = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
    except OSError:
        return
    for child in children:
        if len(out) >= MAX_ENTRIES:
            return
        if not show_hidden and child.name.startswith("."):
            continue
        if child.name in agentlib.DEFAULT_EXCLUDES:
            continue
        out.append({"path": str(child.relative_to(root.parent)),
                    **entry(child)})
        if child.is_dir() and depth > 1:
            tree(child, depth - 1, show_hidden, out, prefix + "  ")


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--tree", action="store_true", help="recursive listing")
    p.add_argument("--depth", type=int, default=3, help="tree depth (default 3)")
    p.add_argument("--all", action="store_true", help="include hidden files")
    p.add_argument("--max", type=int, default=MAX_ENTRIES)
    args = p.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        agentlib.die(f"not a directory: {args.path}", 2)

    if args.tree:
        out = []
        tree(root, args.depth, args.all, out)
        agentlib.emit({"root": str(root), "depth": args.depth,
                       "count": len(out), "entries": out,
                       "capped": len(out) >= args.max})
        return 0

    try:
        children = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
    except OSError as exc:
        agentlib.die(f"cannot list {root}: {exc}")
    entries = []
    for c in children:
        if not args.all and c.name.startswith("."):
            continue
        if c.name in agentlib.DEFAULT_EXCLUDES:
            continue
        entries.append({"path": c.name, **entry(c)})
        if len(entries) >= args.max:
            break
    agentlib.emit({"path": str(root), "count": len(entries), "entries": entries,
                   "capped": len(children) > args.max})
    return 0


if __name__ == "__main__":
    sys.exit(main())
