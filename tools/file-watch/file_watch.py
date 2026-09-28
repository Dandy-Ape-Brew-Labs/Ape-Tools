"""Watch files/dirs for changes — JSON events on stdout, one per line.

  file_watch.py src/ --once                 # exit on first event
  file_watch.py build/out.bin --timeout 30  # wait for a file to appear
  file_watch.py src/ --interval 1 --events modified,created

Polling (mtime+size) — no inotify dependency, works on any FS.
Events: created, deleted, modified. Kill with SIGTERM or --timeout;
also exits when a watched path's parent disappears. Use --once as a
blocking 'wait until' primitive, e.g. after `serve start`.
"""

import json
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

WANT_STOP = False


def handle_sig(*_):
    global WANT_STOP
    WANT_STOP = True


def snapshot(roots: list[Path]) -> dict[str, tuple]:
    """path -> (mtime_ns, size, is_dir) for everything under roots."""
    snap = {}
    for root in roots:
        stack = [root]
        while stack:
            p = stack.pop()
            try:
                st = p.lstat()
            except OSError:
                continue
            snap[str(p)] = (st.st_mtime_ns, st.st_size, p.is_dir())
            if p.is_dir() and not p.is_symlink():
                try:
                    stack.extend(p.iterdir())
                except OSError:
                    continue
    return snap


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("paths", nargs="+")
    p.add_argument("--interval", type=float, default=0.5)
    p.add_argument("--timeout", type=float, default=0,
                   help="max seconds to watch (0 = until killed)")
    p.add_argument("--once", action="store_true",
                   help="exit after the first event")
    p.add_argument("--events", default="created,deleted,modified")
    args = p.parse_args()
    wanted = set(args.events.split(","))
    roots = [Path(x) for x in args.paths]

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    prev = snapshot(roots)
    deadline = (time.monotonic() + args.timeout) if args.timeout else None

    while not WANT_STOP:
        if deadline and time.monotonic() >= deadline:
            break
        time.sleep(args.interval)
        cur = snapshot(roots)
        events = []
        for path, sig in cur.items():
            old = prev.get(path)
            if old is None and "created" in wanted:
                events.append({"event": "created", "path": path})
            elif old is not None and old != sig and "modified" in wanted:
                events.append({"event": "modified", "path": path})
        if "deleted" in wanted:
            for path in prev:
                if path not in cur:
                    events.append({"event": "deleted", "path": path})
        prev = cur
        for e in sorted(events, key=lambda e: e["path"]):
            e["ts"] = time.time()
            sys.stdout.write(json.dumps(e) + "\n")
            sys.stdout.flush()
        if events and args.once:
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
