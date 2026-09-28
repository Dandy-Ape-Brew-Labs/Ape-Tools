"""Background process manager — start, read, write, kill, list.

Each process gets a registry dir under $AGENT_TOOLS_HOME/procs/<id>/ with
stdout.log, stderr.log, exit, meta.json and a stdin FIFO.

  proc.py start "npm run dev" --cwd /repo        # prints proc id
  proc.py read <id> --tail 50                    # poll output
  proc.py write <id> --text "y\n"                # feed stdin
  proc.py list                                   # all tracked procs
  proc.py kill <id>                              # SIGTERM then SIGKILL group
"""

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def proc_dir(pid: str) -> Path:
    return agentlib.state_dir("procs") / pid


def load_meta(pid: str) -> dict:
    d = proc_dir(pid)
    meta = agentlib.read_json(d / "meta.json")
    if meta is None:
        agentlib.die(f"unknown proc '{pid}'", 2)
    return meta


def proc_status(pid: str) -> dict:
    d = proc_dir(pid)
    meta = load_meta(pid)
    exit_file = d / "exit"
    status = {
        "id": pid, "cmd": meta["cmd"], "pid": meta["pid"],
        "started_at": meta["started_at"],
    }
    if exit_file.exists():
        status["status"] = "exited"
        status["exit"] = int(exit_file.read_text().strip() or -1)
        return status
    try:
        os.kill(meta["pid"], 0)
        status["status"] = "running"
    except ProcessLookupError:
        status["status"] = "gone"
        status["exit"] = None
    except PermissionError:
        status["status"] = "running"
    return status


def cmd_start(args) -> int:
    pid = uuid.uuid4().hex[:12]
    d = proc_dir(pid)
    d.mkdir(parents=True, exist_ok=True)
    fifo = d / "stdin.fifo"
    os.mkfifo(fifo)
    wrapper = (
        f"{{ cd {json.dumps(str(Path(args.cwd).resolve()))} && {{ {args.command} ; }}; }} "
        f"> stdout.log 2> stderr.log; echo $? > exit"
    )
    # O_RDWR keeps the FIFO open: no EOF when writers detach, and the
    # child's blocking reads wait for input rather than seeing EAGAIN.
    fifo_fd = os.open(fifo, os.O_RDWR)
    proc = subprocess.Popen(
        ["bash", "-c", wrapper],
        cwd=d, stdin=fifo_fd, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    agentlib.write_json(d / "meta.json", {
        "id": pid, "cmd": args.command, "cwd": str(Path(args.cwd).resolve()),
        "pid": proc.pid, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    agentlib.emit({"id": pid, "pid": proc.pid, "dir": str(d),
                   "hint": f"read output: proc.py read {pid}"})
    return 0


def cmd_read(args) -> int:
    status = proc_status(args.id)
    d = proc_dir(args.id)
    for name in ("stdout", "stderr"):
        data = (d / f"{name}.log")
        text = data.read_text(errors="replace") if data.exists() else ""
        if args.since is not None and name == "stdout":
            status["stdout_new"] = text[args.since:]
            status["offset"] = len(text.encode())
        if args.tail is not None:
            lines = text.splitlines()
            status[name] = "\n".join(lines[-args.tail:])
            status[f"{name}_bytes"] = len(text.encode())
        else:
            t, trunc = agentlib.head_tail(text)
            status[name] = t
            status[f"{name}_truncated"] = trunc
    agentlib.emit(status)
    return 0


def cmd_write(args) -> int:
    status = proc_status(args.id)
    if status["status"] != "running":
        agentlib.die(f"proc {args.id} is {status['status']}", 1)
    fifo = proc_dir(args.id) / "stdin.fifo"
    data = args.text if args.text is not None else sys.stdin.read()
    fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(fd, data.encode())
    finally:
        os.close(fd)
    agentlib.emit({"id": args.id, "bytes": len(data.encode())})
    return 0


def cmd_list(args) -> int:
    procs = [proc_status(d.name) for d in agentlib.state_dir("procs").iterdir()
             if (d / "meta.json").exists()]
    agentlib.emit(procs)
    return 0


def cmd_kill(args) -> int:
    status = proc_status(args.id)
    meta = load_meta(args.id)
    if status["status"] != "running":
        agentlib.emit({"id": args.id, "status": status["status"], "note": "not running"})
        return 0
    try:
        os.killpg(meta["pid"], signal.SIGTERM)
    except (ProcessLookupError, PermissionError) as exc:
        agentlib.die(f"cannot signal proc: {exc}")
    for _ in range(50):
        if (proc_dir(args.id) / "exit").exists():
            break
        try:
            os.kill(meta["pid"], 0)
            time.sleep(0.1)
        except ProcessLookupError:
            break
    else:
        os.killpg(meta["pid"], signal.SIGKILL)
    # killpg kills the wrapper too, so 'exit' may never be written —
    # record the signal-death code so status reads as "exited".
    exit_file = proc_dir(args.id) / "exit"
    if not exit_file.exists():
        exit_file.write_text("143")
    agentlib.emit({"id": args.id, "killed": True})
    return 0


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("command"); s.add_argument("--cwd", default=".")
    r = sub.add_parser("read"); r.add_argument("id")
    r.add_argument("--tail", type=int); r.add_argument("--since", type=int,
        help="stdout byte offset — print only new bytes")
    w = sub.add_parser("write"); w.add_argument("id"); w.add_argument("--text")
    sub.add_parser("list")
    k = sub.add_parser("kill"); k.add_argument("id")
    args = p.parse_args()
    return {"start": cmd_start, "read": cmd_read, "write": cmd_write,
            "list": cmd_list, "kill": cmd_kill}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
