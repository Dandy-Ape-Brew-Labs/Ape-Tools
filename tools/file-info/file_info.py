"""Report file metadata: size, mtime, mode, type, line count, mime.

Check size before reading an unknown file (logs, dumps, bundles).
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("paths", nargs="+", help="files or directories")
    args = p.parse_args()

    out = []
    rc = 0
    for raw in args.paths:
        path = Path(raw)
        if not path.exists():
            print(f"warn: not found: {path}", file=sys.stderr)
            rc = 1
            continue
        st = path.stat()
        info = {
            "path": str(path.resolve()),
            "name": path.name,
            "type": "directory" if path.is_dir() else ("symlink" if path.is_symlink() else "file"),
            "size_bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
            "mode": oct(st.st_mode & 0o777),
        }
        if path.is_file():
            info["mime"] = agentlib.guess_mime(path)
            info["binary"] = agentlib.is_binary(path)
            if not info["binary"]:
                try:
                    with path.open("rb") as fh:
                        info["lines"] = sum(
                            chunk.count(b"\n")
                            for chunk in iter(lambda: fh.read(1 << 20), b"")
                        )
                except OSError:
                    info["lines"] = None
        else:
            try:
                info["entries"] = sum(1 for _ in path.iterdir())
            except OSError:
                info["entries"] = None
        out.append(info)

    agentlib.emit(out[0] if len(out) == 1 else out)
    return rc


if __name__ == "__main__":
    sys.exit(main())
