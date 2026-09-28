"""Execute Python code — a snippet (-c) or a file — in the repo venv.

  py_run.py -c "import sys; print(sys.version)"
  py_run.py script.py --arg x
  py_run.py --cwd /tmp -c "print(2+2)"

Uses `uv run python` when the repo venv has dependencies; for a persistent
REPL use `proc start "python3 -i"` + `proc write`.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("target", help="script path or code (with -c)")
    p.add_argument("script_args", nargs="*", help="args passed to the script")
    p.add_argument("-c", "--code", action="store_true",
                   help="treat target as code, not a file")
    p.add_argument("--cwd", default=".")
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--system", action="store_true",
                   help="use system python3 instead of the repo venv")
    args = p.parse_args()

    if args.system or not agentlib.which("uv"):
        argv = ["python3"]
    else:
        argv = ["uv", "run", "--quiet", "python"]
    if args.code:
        argv += ["-c", args.target]
    else:
        script = Path(args.target)
        if not script.is_file():
            agentlib.die(f"not a file: {script} (use -c for inline code)", 2)
        argv += [str(script)] + list(args.script_args)

    res = agentlib.run_cmd(argv, cwd=args.cwd, timeout=args.timeout)
    out, t1 = agentlib.head_tail(res["stdout"])
    err, t2 = agentlib.head_tail(res["stderr"])
    agentlib.emit({
        "exit": res["exit"], "stdout": out, "stderr": err,
        "duration_ms": res["duration_ms"], "truncated": t1 or t2,
        "interpreter": argv[0] if args.system else "uv run python",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
