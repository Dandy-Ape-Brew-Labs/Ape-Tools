"""Human-facing notifications: desktop notify-send plus a file outbox.

  notify.py send --title "Task done" --body "details"
  notify.py outbox                    # list $AGENT_TOOLS_HOME/outbox/*.json
  notify.py finish --message "done"   # terminal 'finish' signal for agent loops

Every send appends to the outbox so nothing is lost if the desktop
notification is missed or the session is headless.
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def outbox() -> Path:
    return agentlib.state_dir("outbox")


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
    s.add_argument("--title", required=True)
    s.add_argument("--body", default="")

    sub.add_parser("outbox")

    f = sub.add_parser("finish")
    f.add_argument("--message", required=True)
    args = p.parse_args()

    if args.cmd == "send":
        sent = desktop_notify(args.title, args.body)
        entry = {"ts": time.time(), "title": args.title,
                 "body": args.body, "desktop": sent}
        path = outbox() / f"{int(entry['ts']*1000)}.json"
        agentlib.write_json(path, entry)
        agentlib.emit({"notified": True, "desktop": sent,
                       "outbox": str(path)})
        return 0

    if args.cmd == "outbox":
        items = [json.loads(f.read_text())
                 for f in sorted(outbox().glob("*.json"))]
        agentlib.emit(items)
        return 0

    if args.cmd == "finish":
        desktop_notify("Agent finished", args.message)
        agentlib.emit({"finished": True, "message": args.message})
        return 0


if __name__ == "__main__":
    sys.exit(main())
