"""Run a shell command with timeout and capped output.

  run_shell.py "pytest -x -q" --timeout-ms 300000
  run_shell.py "make build" --cwd /repo --max-bytes 50000

Always set a timeout. Prefer non-interactive flags in the command itself
(-y, --no-input, CI=1). Output is truncated head+tail.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("command", help="command string (run via bash -c)")
    p.add_argument("--cwd", default=".", help="working directory")
    p.add_argument("--timeout-ms", type=int, default=30000,
                   help="kill after N ms (default 30000)")
    p.add_argument("--max-bytes", type=int, default=64 * 1024,
                   help="per-stream output cap (default 65536)")
    args = p.parse_args()

    start = time.monotonic()
    try:
        proc = subprocess.run(
            ["bash", "-c", args.command],
            cwd=args.cwd, capture_output=True, text=True,
            timeout=args.timeout_ms / 1000,
        )
        result = {
            "exit": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "exit": 124,
            "stdout": exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            "stderr": f"timed out after {args.timeout_ms}ms",
        }
        print(f"warn: timed out after {args.timeout_ms}ms", file=sys.stderr)

    out, t1 = agentlib.head_tail(result["stdout"], args.max_bytes)
    err, t2 = agentlib.head_tail(result["stderr"], args.max_bytes)
    agentlib.emit({
        "exit": result["exit"],
        "stdout": out,
        "stderr": err,
        "duration_ms": int((time.monotonic() - start) * 1000),
        "truncated": t1 or t2,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
