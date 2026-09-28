"""Deliver a produced file to the user — copy it into the notify
outbox, drop a desktop notification with the path, optionally open it.

  send_file.py send dist/report.pdf [--name report] [--open]
  send_file.py list                     # everything delivered

Files land in $AGENT_TOOLS_HOME/outbox/files/<ts>-<name> and a JSON
record (same shape notify uses) is appended to the outbox, so
`notify.py outbox` shows deliveries too.
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def files_dir() -> Path:
    return agentlib.state_dir("outbox", "files")


def desktop_notify(title: str, body: str) -> bool:
    if not shutil.which("notify-send"):
        return False
    subprocess.run(["notify-send", "-a", "agent-tools", title, body],
                   stderr=subprocess.DEVNULL, check=False)
    return True


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("path")
    s.add_argument("--name", help="deliver under this name instead")
    s.add_argument("--open", action="store_true",
                   help="also xdg-open the delivered file")
    s.add_argument("--title", default="File ready")
    sub.add_parser("list")
    args = p.parse_args()

    if args.cmd == "send":
        src = Path(args.path).resolve()
        if not src.is_file():
            agentlib.die(f"not a file: {src}", 2)
        name = args.name or src.name
        if "/" in name or name in ("", ".", ".."):
            agentlib.die(f"bad --name '{name}'", 2)
        dest = files_dir() / f"{int(time.time()*1000)}-{name}"
        shutil.copy2(src, dest)
        sent = desktop_notify(args.title, str(dest))
        record = {"ts": time.time(), "title": args.title,
                  "body": str(dest), "file": str(dest),
                  "source": str(src), "desktop": sent}
        agentlib.write_json(
            agentlib.state_dir("outbox") / f"{int(record['ts']*1000)}-file.json",
            record)
        opened = False
        if args.open and shutil.which("xdg-open"):
            opened = subprocess.run(
                ["xdg-open", str(dest)],
                stderr=subprocess.DEVNULL).returncode == 0
        agentlib.emit({"delivered": str(dest), "notified": sent,
                       "opened": opened})
        return 0

    if args.cmd == "list":
        out = [{"file": str(f), "bytes": f.stat().st_size,
                "mtime": f.stat().st_mtime}
               for f in sorted(files_dir().iterdir()) if f.is_file()]
        agentlib.emit(out)
        return 0


if __name__ == "__main__":
    sys.exit(main())
