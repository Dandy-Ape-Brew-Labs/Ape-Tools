"""Capture the screen on KDE Plasma/Wayland — spectacle first, then
KWin DBus screenshot, then gnome-screenshot as fallbacks.

  gui_screen.py shot [--out file.png] [--window | --region | --monitor N]
  gui_screen.py backends            # which capture tools exist

Returns JSON {path, bytes, backend} — feed the path to file-media or
an image-capable model.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def backends() -> dict:
    return {
        "spectacle": bool(shutil.which("spectacle")),
        "gnome-screenshot": bool(shutil.which("gnome-screenshot")),
        "imagemagick-import": bool(shutil.which("import")),
        "grim": bool(shutil.which("grim")),
    }


def capture(out: Path, args) -> str | None:
    """Return backend name on success."""
    if shutil.which("spectacle"):
        cmd = ["spectacle", "-b", "-n", "-o", str(out)]
        if args.window:
            cmd += ["-a"]            # active window
        elif args.region:
            cmd += ["-r"]            # region (interactive picker)
        elif args.monitor is not None:
            cmd += ["-m", str(args.monitor)]
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        if r.returncode == 0 and out.exists() and out.stat().st_size:
            return "spectacle"
    if shutil.which("grim"):         # wlroots compositors
        r = subprocess.run(["grim", str(out)], capture_output=True,
                           timeout=30)
        if r.returncode == 0 and out.exists() and out.stat().st_size:
            return "grim"
    if shutil.which("gnome-screenshot"):
        cmd = ["gnome-screenshot", "-f", str(out)]
        if args.window:
            cmd.append("-w")
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        if r.returncode == 0 and out.exists() and out.stat().st_size:
            return "gnome-screenshot"
    return None


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backends")
    s = sub.add_parser("shot")
    s.add_argument("--out")
    s.add_argument("--window", action="store_true")
    s.add_argument("--region", action="store_true")
    s.add_argument("--monitor", type=int)
    args = p.parse_args()

    if args.cmd == "backends":
        agentlib.emit(backends())
        return 0

    if not any(backends().values()):
        agentlib.die(
            "no screenshot backend. On KDE/Wayland: install spectacle. "
            "See README for other compositors.", 3)

    out = Path(args.out) if args.out else Path(
        tempfile.mkstemp(suffix=".png", prefix="gui-screen-")[1])
    backend = capture(out, args)
    if backend is None:
        agentlib.die("all capture backends failed (headless session?)", 1)
    agentlib.emit({"path": str(out.resolve()),
                   "bytes": out.stat().st_size, "backend": backend})
    return 0


if __name__ == "__main__":
    sys.exit(main())
