"""Schedule agent runs with systemd user timers (transient units named
agent-tools-<name>.*). No daemon needed — systemd does the firing.

  schedule.py once --in 30m --command "echo hi" [--name sync]
  schedule.py once --at "2026-09-01 09:00" --command "..."
  schedule.py recurring --calendar "*:0/15" --command "..."
  schedule.py list
  schedule.py cancel <name>

Times like --in accept systemd spans: 30s, 15min, 2h, "1h 30min".
"""

import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

PREFIX = "agent-tools-"


def systemd_run(unit: str, trigger_args: list[str],
                command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemd-run", "--user", f"--unit={unit}", *trigger_args,
         "/bin/sh", "-c", command],
        capture_output=True, text=True)


def check_user_manager() -> None:
    if subprocess.run(["systemctl", "--user", "is-system-running"],
                      capture_output=True).returncode not in (0, 1):
        agentlib.die("systemd --user manager unavailable "
                     "(loginctl enable-linger helps on headless)", 2)


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("once", "recurring"):
        s = sub.add_parser(name)
        s.add_argument("--in", dest="span")
        s.add_argument("--at")
        s.add_argument("--calendar")
        s.add_argument("--command", required=True)
        s.add_argument("--name")
    sub.add_parser("list")
    c = sub.add_parser("cancel"); c.add_argument("name")
    args = p.parse_args()

    check_user_manager()

    if args.cmd in ("once", "recurring"):
        if args.cmd == "once" and not (args.span or args.at):
            agentlib.die("once needs --in SPAN or --at 'YYYY-MM-DD HH:MM'", 2)
        if args.cmd == "recurring" and not args.calendar:
            agentlib.die("recurring needs --calendar SPEC", 2)
        name = args.name or f"{args.cmd}-{int(time.time())}"
        if not re.fullmatch(r"[\w.-]+", name):
            agentlib.die("name must match [\\w.-]+", 2)
        unit = PREFIX + name
        trig = (["--on-calendar", args.at] if args.at else
                ["--on-calendar", args.calendar] if args.calendar else
                ["--on-active", args.span])
        r = systemd_run(unit, trig, args.command)
        if r.returncode != 0:
            agentlib.die(f"systemd-run failed: {r.stderr.strip()}", 1)
        agentlib.emit({"unit": unit, "scheduled": args.command})
        return 0

    if args.cmd == "list":
        r = subprocess.run(["systemctl", "--user", "list-timers",
                            f"{PREFIX}*", "--no-pager", "--no-legend"],
                           capture_output=True, text=True)
        agentlib.emit({"raw": r.stdout.strip()})
        return 0

    if args.cmd == "cancel":
        unit = PREFIX + args.name
        for suf in ("timer", "service"):
            subprocess.run(["systemctl", "--user", "stop",
                            f"{unit}.{suf}"],
                           capture_output=True, check=False)
        subprocess.run(["systemctl", "--user", "reset-failed", unit],
                       capture_output=True, check=False)
        agentlib.emit({"cancelled": unit})
        return 0


if __name__ == "__main__":
    sys.exit(main())
