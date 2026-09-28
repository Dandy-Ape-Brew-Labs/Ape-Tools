"""Open files/URLs in the user's desktop applications (xdg-open).

  open.py open report.pdf            # default app for the file type
  open.py open https://example.com   # default browser
  open.py open --reveal out/result.png   # show in file manager
  open.py mime report.pdf            # file type + registered handler

Exits 3 on headless sessions (no DISPLAY/WAYLAND_DISPLAY).
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def session_ok() -> bool:
    return bool(os.environ.get("DISPLAY")
                or os.environ.get("WAYLAND_DISPLAY"))


def xdg(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=30)


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open")
    o.add_argument("target", nargs="?")
    o.add_argument("--reveal", metavar="PATH",
                   help="open the containing folder in the file manager")
    m = sub.add_parser("mime"); m.add_argument("path")
    args = p.parse_args()

    if not agentlib.which("xdg-open"):
        agentlib.die("xdg-open not found — install xdg-utils", 3)

    if args.cmd == "mime":
        if not agentlib.which("xdg-mime"):
            agentlib.die("xdg-mime not found — install xdg-utils", 3)
        path = Path(args.path)
        if not path.exists():
            agentlib.die(f"not found: {path}", 2)
        ftype = xdg(["xdg-mime", "query", "filetype", str(path)])
        default = ""
        if ftype.returncode == 0 and ftype.stdout.strip():
            d = xdg(["xdg-mime", "query", "default", ftype.stdout.strip()])
            default = d.stdout.strip() if d.returncode == 0 else ""
        agentlib.emit({"path": str(path),
                       "mime": ftype.stdout.strip() or None,
                       "default_handler": default or None})
        return 0

    if args.cmd == "open":
        if not session_ok():
            agentlib.die("headless session (no DISPLAY/WAYLAND_DISPLAY) — "
                         "nothing to open on", 3)
        if args.reveal:
            path = Path(args.reveal).resolve()
            if not path.exists():
                agentlib.die(f"not found: {path}", 2)
            target = str(path.parent if path.is_file() else path)
        else:
            if not args.target:
                agentlib.die("open needs a target path or URL", 2)
            target = args.target
            if not (target.startswith(("http://", "https://", "file://"))
                    or Path(target).exists()):
                agentlib.die(f"not found: {target}", 2)
        r = xdg(["xdg-open", target])
        if r.returncode != 0:
            agentlib.die(f"xdg-open failed: {r.stderr.strip()}", 1)
        agentlib.emit({"opened": target, "reveal": bool(args.reveal)})
        return 0


if __name__ == "__main__":
    sys.exit(main())
