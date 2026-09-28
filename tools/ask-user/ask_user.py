"""Ask the human a question via file handoff + desktop notification.
The agent never blocks the terminal — it asks (optionally waits), the
human or another process writes the answer file, the agent reads it.

  ask_user.py ask --question "Ship to prod?" --options "yes,no" --timeout 600
  ask_user.py answer <id> --text "yes"          # or --option 1
  ask_user.py list [--pending]
  ask_user.py read <id>

ask writes $AGENT_TOOLS_HOME/questions/<id>.json and waits (default
30 min) for answers/<id>.json. Exit 0 on answer, 3 on timeout.
"""

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def qdir() -> Path:
    return agentlib.state_dir("questions")


def adir() -> Path:
    return agentlib.state_dir("answers")


def answer_for(qid: str) -> dict | None:
    f = adir() / f"{qid}.json"
    if f.exists():
        return json.loads(f.read_text())
    return None


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask")
    a.add_argument("--question", required=True)
    a.add_argument("--options", help="comma-separated choices")
    a.add_argument("--timeout", type=int, default=1800)
    a.add_argument("--no-notify", action="store_true")

    n = sub.add_parser("answer"); n.add_argument("id")
    n.add_argument("--text"); n.add_argument("--option", type=int)

    l = sub.add_parser("list")
    l.add_argument("--pending", action="store_true")

    r = sub.add_parser("read"); r.add_argument("id")
    args = p.parse_args()

    if args.cmd == "ask":
        qid = uuid.uuid4().hex[:8]
        q = {"id": qid, "question": args.question,
             "options": (args.options or "").split(",") if args.options else None,
             "ts": time.time()}
        agentlib.write_json(qdir() / f"{qid}.json", q)
        if not args.no_notify:
            subprocess.run(["notify-send", "-a", "agent-tools",
                            "Agent asks", args.question],
                           stderr=subprocess.DEVNULL, check=False)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            ans = answer_for(qid)
            if ans is not None:
                agentlib.emit({"id": qid, "question": args.question,
                               "answer": ans.get("answer")})
                return 0
            time.sleep(1)
        agentlib.emit({"id": qid, "timeout": True,
                       "hint": f"answer with: ask_user.py answer {qid} --text '...'"})
        return 3

    if args.cmd == "answer":
        qf = qdir() / f"{args.id}.json"
        if not qf.exists():
            agentlib.die(f"no question '{args.id}'", 2)
        q = json.loads(qf.read_text())
        if args.option is not None and q.get("options"):
            if not 1 <= args.option <= len(q["options"]):
                agentlib.die(f"option must be 1..{len(q['options'])}", 2)
            text = q["options"][args.option - 1]
        else:
            text = args.text if args.text is not None else sys.stdin.read()
        agentlib.write_json(adir() / f"{args.id}.json",
                            {"id": args.id, "answer": text, "ts": time.time()})
        agentlib.emit({"answered": args.id, "answer": text})
        return 0

    if args.cmd == "list":
        out = []
        for f in sorted(qdir().glob("*.json")):
            q = json.loads(f.read_text())
            ans = answer_for(q["id"])
            if args.pending and ans is not None:
                continue
            q["answer"] = ans.get("answer") if ans else None
            out.append(q)
        agentlib.emit(out)
        return 0

    if args.cmd == "read":
        qf = qdir() / f"{args.id}.json"
        if not qf.exists():
            agentlib.die(f"no question '{args.id}'", 2)
        q = json.loads(qf.read_text())
        ans = answer_for(args.id)
        q["answer"] = ans.get("answer") if ans else None
        agentlib.emit(q)
        return 0


if __name__ == "__main__":
    sys.exit(main())
