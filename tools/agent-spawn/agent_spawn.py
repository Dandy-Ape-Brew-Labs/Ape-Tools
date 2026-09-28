"""Spawn a sub-agent via an installed agent CLI (claude, gemini) and
capture its output — synchronous fan-out for delegating subtasks.

  agent_spawn.py run "summarize src/auth.py" [--backend claude|gemini|auto]
                                              [--cwd DIR] [--timeout 600]
  agent_spawn.py backends          # which CLIs are installed
  agent_spawn.py run "..." --dangerous   # skip permission prompts (claude)

Auto backend prefers claude, falls back to gemini. Exit code mirrors
the child's for run failures.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

BACKENDS = {
    "claude": lambda prompt, dangerous: (
        ["claude", "-p", prompt]
        + (["--dangerously-skip-permissions"] if dangerous else [])),
    "gemini": lambda prompt, dangerous: ["gemini", "-p", prompt],
}


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("backends")
    r = sub.add_parser("run"); r.add_argument("prompt", nargs="?")
    r.add_argument("--prompt", dest="prompt_flag",
                   help="or pass via --prompt/stdin")
    r.add_argument("--backend", default="auto",
                   choices=["auto", *BACKENDS])
    r.add_argument("--cwd", default=".")
    r.add_argument("--timeout", type=int, default=600)
    r.add_argument("--dangerous", action="store_true",
                   help="claude: --dangerously-skip-permissions")
    args = p.parse_args()

    if args.cmd == "backends":
        agentlib.emit({b: bool(shutil.which(b)) for b in BACKENDS})
        return 0

    prompt = args.prompt or args.prompt_flag or sys.stdin.read()
    if not prompt.strip():
        agentlib.die("empty prompt", 2)

    backend = args.backend
    if backend == "auto":
        backend = next((b for b in BACKENDS if shutil.which(b)), None)
        if backend is None:
            agentlib.die("no agent CLI found (install claude or gemini)", 2)
    elif not shutil.which(backend):
        agentlib.die(f"backend '{backend}' not installed", 2)

    cmd = BACKENDS[backend](prompt, args.dangerous)
    try:
        proc = subprocess.run(cmd, cwd=args.cwd, capture_output=True,
                              text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        agentlib.die(f"{backend} timed out after {args.timeout}s", 4)
    agentlib.emit({"backend": backend, "exit": proc.returncode,
                   "output": proc.stdout.strip(),
                   "stderr": proc.stderr.strip()})
    return 0 if proc.returncode == 0 else 5


if __name__ == "__main__":
    sys.exit(main())
