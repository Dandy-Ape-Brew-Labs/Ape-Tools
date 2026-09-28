"""System clipboard for local agents — get/set/clear.

  clipboard.py get                 # print clipboard contents
  clipboard.py set "some text"     # copy text
  clipboard.py set --file out.md   # copy a file's contents
  clipboard.py clear
  clipboard.py backends            # which clipboard tools exist

Backend order: wl-copy/wl-paste (Wayland) -> xclip -> xsel.
Override with $CLIPBOARD_BACKEND=wl|xclip|xsel.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

BACKENDS = {
    "wl": {"bins": ["wl-copy", "wl-paste"],
           "get": ["wl-paste", "-n"], "set": ["wl-copy"]},
    "xclip": {"bins": ["xclip"],
              "get": ["xclip", "-selection", "clipboard", "-o"],
              "set": ["xclip", "-selection", "clipboard", "-i"]},
    "xsel": {"bins": ["xsel"],
             "get": ["xsel", "-b", "-o"], "set": ["xsel", "-b", "-i"]},
}
HINT = ("sudo dnf install wl-clipboard   # Wayland (KDE)\n"
        "sudo dnf install xclip          # X11")


def available() -> dict:
    return {name: all(shutil.which(b) for b in spec["bins"])
            for name, spec in BACKENDS.items()}


def pick() -> str | None:
    forced = os.environ.get("CLIPBOARD_BACKEND")
    for name, ok in available().items():
        if forced:
            if name == forced and ok:
                return name
        elif ok:
            return name
    return None


def run(argv: list[str], input_data: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=input_data, capture_output=True,
                          timeout=15)


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("get")
    s = sub.add_parser("set")
    s.add_argument("text", nargs="?")
    s.add_argument("--file")
    sub.add_parser("clear")
    sub.add_parser("backends")
    args = p.parse_args()

    if args.cmd == "backends":
        agentlib.emit({"available": available(), "selected": pick(),
                       "session": os.environ.get("XDG_SESSION_TYPE"),
                       "hint": HINT})
        return 0

    backend = pick()
    if backend is None:
        agentlib.die("no clipboard tool found on PATH.\n" + HINT, 3)
    spec = BACKENDS[backend]

    if args.cmd == "get":
        r = run(spec["get"])
        if r.returncode != 0:
            agentlib.die(f"{spec['get'][0]} failed: "
                         f"{r.stderr.decode(errors='replace').strip()}", 1)
        sys.stdout.buffer.write(r.stdout)
        if not r.stdout:
            print("note: clipboard empty", file=sys.stderr)
        return 0

    if args.cmd in ("set", "clear"):
        if args.cmd == "clear":
            data = b""
        elif args.file:
            data = Path(args.file).read_bytes()
        elif args.text is not None:
            data = args.text.encode()
        else:
            data = sys.stdin.buffer.read()
        r = run(spec["set"], input_data=data)
        if r.returncode != 0:
            agentlib.die(f"{spec['set'][0]} failed: "
                         f"{r.stderr.decode(errors='replace').strip()}", 1)
        agentlib.emit({"set": args.cmd == "set", "cleared": args.cmd == "clear",
                       "backend": backend, "bytes": len(data)})
        return 0


if __name__ == "__main__":
    sys.exit(main())
