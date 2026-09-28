"""Share a file or directory over local HTTP — artifact delivery and
quick LAN shares. Servers are spawned through the proc registry, so
`proc.py list` / `proc.py kill` manage them.

  serve.py serve dist/site --port 8080      # http://127.0.0.1:8080/
  serve.py serve out/report.pdf             # serves parent dir, prints file URL
  serve.py serve exports/ --lan             # share on LAN (warn: no auth!)
  serve.py list                             # running shares
  serve.py stop <proc-id>

QR code for the URL when qrencode is installed (great for phone access).
"""

import json
import shlex
import shutil
import socket
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

PROC = agentlib.REPO_ROOT / "tools" / "proc" / "proc.py"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))  # no traffic; just route lookup
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def qr(url: str) -> str | None:
    if not shutil.which("qrencode"):
        return None
    r = subprocess.run(["qrencode", "-t", "UTF8", url],
                       capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else None


def proc_call(*argv: str) -> dict:
    r = agentlib.run_cmd([sys.executable, str(PROC), *argv], timeout=15)
    if r["exit"] != 0:
        agentlib.die(f"proc {' '.join(argv)} failed: {r['stderr'].strip()}", 1)
    return json.loads(r["stdout"])


def cmd_serve(args) -> int:
    target = Path(args.path).resolve()
    if not target.exists():
        agentlib.die(f"not found: {target}", 2)
    serve_dir = target if target.is_dir() else target.parent
    port = args.port or free_port()
    bind = "0.0.0.0" if args.lan else "127.0.0.1"
    cmd = (f"{shlex.quote(sys.executable)} -m http.server {port} "
           f"--bind {bind}")
    res = proc_call("start", cmd, "--cwd", str(serve_dir))
    host = lan_ip() if args.lan else "127.0.0.1"
    url = f"http://{host}:{port}/"
    if target.is_file():
        url += urllib.parse.quote(target.name)
    out = {"proc": res["id"], "url": url, "dir": str(serve_dir),
           "lan": args.lan,
           "stop": f"serve.py stop {res['id']}"}
    if args.lan:
        out["warning"] = ("LAN share has no auth — anyone on the network "
                          "can read this directory")
        print("warn: --lan exposes the directory to the whole network",
              file=sys.stderr)
    code = qr(url)
    if code:
        out["qr"] = code
        print(code, file=sys.stderr)
    agentlib.emit(out)
    return 0


def cmd_list() -> int:
    procs = proc_call("list")
    out = [p for p in procs if "http.server" in p.get("cmd", "")]
    agentlib.emit(out)
    return 0


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("path")
    s.add_argument("--port", type=int, default=0,
                   help="0 picks a free ephemeral port")
    s.add_argument("--lan", action="store_true",
                   help="bind 0.0.0.0 — share on the local network")
    sub.add_parser("list")
    st = sub.add_parser("stop"); st.add_argument("id")
    args = p.parse_args()

    if args.cmd == "serve":
        return cmd_serve(args)
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "stop":
        agentlib.emit(proc_call("kill", args.id))
        return 0


if __name__ == "__main__":
    sys.exit(main())
