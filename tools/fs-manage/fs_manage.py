"""Filesystem operations: mkdir, move, copy, delete.

Delete is recoverable by default — targets move into the state dir's
trash/ folder. --permanent does a real removal (use with care).

  fs_manage.py mkdir a/b/c
  fs_manage.py move old.py new.py
  fs_manage.py copy dir/ backup/ --recursive
  fs_manage.py delete junk.txt            # -> trash
  fs_manage.py delete junk.txt --permanent
"""

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("action", choices=["mkdir", "move", "copy", "delete"])
    p.add_argument("source", help="path (mkdir/delete) or source (move/copy)")
    p.add_argument("dest", nargs="?", help="destination (move/copy only)")
    p.add_argument("--recursive", action="store_true",
                   help="copy/delete directories recursively")
    p.add_argument("--force", action="store_true",
                   help="overwrite existing destination (move/copy)")
    p.add_argument("--permanent", action="store_true",
                   help="delete really removes instead of moving to trash")
    args = p.parse_args()

    src = Path(args.source)

    if args.action == "mkdir":
        src.mkdir(parents=True, exist_ok=True)
        agentlib.emit({"action": "mkdir", "path": str(src.resolve())})
        return 0

    if args.action == "delete":
        if not src.exists():
            agentlib.die(f"not found: {src}", 2)
        if args.permanent:
            if src.is_dir():
                if not args.recursive:
                    agentlib.die("directory needs --recursive", 2)
                shutil.rmtree(src)
            else:
                src.unlink()
            agentlib.emit({"action": "delete", "path": str(src), "permanent": True})
            return 0
        trash = agentlib.state_dir("trash") / f"{int(time.time())}-{src.name}"
        shutil.move(str(src), str(trash))
        agentlib.emit({"action": "delete", "path": str(src),
                       "trashed_to": str(trash), "recoverable": True})
        return 0

    # move / copy
    if not args.dest:
        agentlib.die(f"{args.action} needs a destination", 2)
    dst = Path(args.dest)
    if not src.exists():
        agentlib.die(f"source not found: {src}", 2)
    if src.is_dir() and args.action == "copy" and not args.recursive:
        agentlib.die("copying a directory needs --recursive", 2)
    if dst.exists() and not args.force:
        agentlib.die(f"destination exists: {dst} (use --force)", 2)

    if args.action == "move":
        shutil.move(str(src), str(dst))
    elif src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=bool(args.force))
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    agentlib.emit({"action": args.action, "from": str(src.resolve()),
                   "to": str(dst.resolve())})
    return 0


if __name__ == "__main__":
    sys.exit(main())
