"""File-backed todo/plan state. Persists in $AGENT_TOOLS_HOME/todos.json —
survives across sessions and context compaction.

  plan_todo.py set --todos '[{"content":"do x","status":"in_progress"}, ...]'
  plan_todo.py list
  plan_todo.py complete 2
  plan_todo.py update 3 --status in_progress
  plan_todo.py clear

Exactly one item may be in_progress at a time.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

VALID = ("pending", "in_progress", "completed")


def store_path() -> Path:
    return agentlib.state_dir() / "todos.json"


def load() -> list[dict]:
    return agentlib.read_json(store_path(), default=[])


def save(todos: list[dict]) -> None:
    active = sum(1 for t in todos if t["status"] == "in_progress")
    if active > 1:
        agentlib.die("only one todo may be in_progress", 2)
    for i, t in enumerate(todos, 1):
        t["id"] = i
    agentlib.write_json(store_path(), todos)


def cmd_set(args):
    import json
    raw = args.todos if args.todos != "-" else sys.stdin.read()
    try:
        todos = json.loads(raw)
    except json.JSONDecodeError as exc:
        agentlib.die(f"invalid todos JSON: {exc}", 2)
    if not isinstance(todos, list):
        agentlib.die("todos must be a JSON array", 2)
    for t in todos:
        if "content" not in t:
            agentlib.die("each todo needs 'content'", 2)
        t["status"] = t.get("status", "pending")
        if t["status"] not in VALID:
            agentlib.die(f"bad status '{t['status']}' ({'/'.join(VALID)})", 2)
    save(todos)
    agentlib.emit({"saved": len(todos)})


def cmd_list(args):
    agentlib.emit(load())


def cmd_update(args):
    todos = load()
    if not 1 <= args.id <= len(todos):
        agentlib.die(f"no todo #{args.id} ({len(todos)} items)", 2)
    if args.status:
        if args.status not in VALID:
            agentlib.die(f"bad status '{args.status}'", 2)
        todos[args.id - 1]["status"] = args.status
    if args.content:
        todos[args.id - 1]["content"] = args.content
    save(todos)
    agentlib.emit(todos)


def cmd_complete(args):
    todos = load()
    if not 1 <= args.id <= len(todos):
        agentlib.die(f"no todo #{args.id}", 2)
    todos[args.id - 1]["status"] = "completed"
    save(todos)
    agentlib.emit(todos)


def cmd_clear(args):
    agentlib.write_json(store_path(), [])
    agentlib.emit({"cleared": True})


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set"); s.add_argument("--todos", required=True,
        help="JSON array or '-' for stdin")
    sub.add_parser("list")
    u = sub.add_parser("update"); u.add_argument("id", type=int)
    u.add_argument("--status", choices=VALID); u.add_argument("--content")
    c = sub.add_parser("complete"); c.add_argument("id", type=int)
    sub.add_parser("clear")
    args = p.parse_args()
    return {"set": cmd_set, "list": cmd_list, "update": cmd_update,
            "complete": cmd_complete, "clear": cmd_clear}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
