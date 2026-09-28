"""Structured git operations — JSON output for agents. Wraps `git` in
the current repo (or --cwd) rather than reimplementing it.

  git_ops.py status [--cwd DIR]
  git_ops.py diff [--cached] [--stat] [--file F]
  git_ops.py log [-n 10] [--oneline]
  git_ops.py commit --message "..." [--files a b]
  git_ops.py branch [--list]
  git_ops.py checkout <ref> | git_ops.py checkout -b <name>
  git_ops.py show <ref> [--stat]
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def git(args: list[str], cwd: str = ".") -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd,
                          capture_output=True, text=True)


def require_repo(cwd: str) -> None:
    r = git(["rev-parse", "--is-inside-work-tree"], cwd)
    if r.returncode != 0:
        agentlib.die(f"not a git repo: {cwd}", 2)


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("--cwd", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    d = sub.add_parser("diff")
    d.add_argument("--cached", action="store_true")
    d.add_argument("--stat", action="store_true")
    d.add_argument("--file")
    l = sub.add_parser("log")
    l.add_argument("-n", type=int, default=10)
    l.add_argument("--oneline", action="store_true")
    c = sub.add_parser("commit")
    c.add_argument("--message", required=True)
    c.add_argument("--files", nargs="*", help="stage these only")
    b = sub.add_parser("branch"); b.add_argument("--list", action="store_true")
    co = sub.add_parser("checkout"); co.add_argument("ref")
    co.add_argument("-b", dest="new_branch", action="store_true")
    s = sub.add_parser("show"); s.add_argument("ref")
    s.add_argument("--stat", action="store_true")
    args = p.parse_args()

    require_repo(args.cwd)
    cwd = args.cwd

    if args.cmd == "status":
        r = git(["status", "--porcelain=v1", "--branch"], cwd)
        lines = r.stdout.splitlines()
        branch = lines[0].removeprefix("## ") if lines and lines[0].startswith("##") else "?"
        files = [{"xy": ln[:2], "path": ln[3:]} for ln in lines[1:] if ln]
        agentlib.emit({"branch": branch, "files": files,
                       "clean": not files})
        return 0

    if args.cmd == "diff":
        g = ["diff"] + (["--cached"] if args.cached else []) \
            + (["--stat"] if args.stat else [])
        if args.file:
            g += ["--", args.file]
        r = git(g, cwd)
        print(r.stdout, end="")
        return r.returncode

    if args.cmd == "log":
        fmt = "--oneline" if args.oneline else \
            "--format=%H%n%an <%ae>%n%ad%n%s%n%b%n---"
        r = git(["log", f"-{args.n}", fmt], cwd)
        if args.oneline:
            print(r.stdout, end="")
        else:
            entries = []
            for block in r.stdout.split("---\n"):
                lines = block.strip("\n").splitlines()
                if len(lines) >= 4:
                    entries.append({"sha": lines[0], "author": lines[1],
                                    "date": lines[2], "subject": lines[3],
                                    "body": "\n".join(lines[4:])})
            agentlib.emit(entries)
        return r.returncode

    if args.cmd == "commit":
        if args.files:
            r = git(["add", "--", *args.files], cwd)
            if r.returncode != 0:
                agentlib.die(f"git add failed: {r.stderr.strip()}", 1)
        r = git(["commit", "-m", args.message], cwd)
        if r.returncode != 0:
            agentlib.die(r.stderr.strip() or r.stdout.strip(), 1)
        agentlib.emit({"committed": True,
                       "output": r.stdout.strip()})
        return 0

    if args.cmd == "branch":
        r = git(["branch", "--list"], cwd)
        branches = [ln.strip().lstrip("* ") for ln in r.stdout.splitlines()]
        cur = next((ln[2:] for ln in r.stdout.splitlines()
                    if ln.startswith("*")), None)
        agentlib.emit({"current": cur, "branches": branches})
        return 0

    if args.cmd == "checkout":
        g = (["checkout", "-b", args.ref] if args.new_branch
             else ["checkout", args.ref])
        r = git(g, cwd)
        if r.returncode != 0:
            agentlib.die(r.stderr.strip(), 1)
        agentlib.emit({"checked_out": args.ref,
                       "created": args.new_branch})
        return 0

    if args.cmd == "show":
        g = ["show", args.ref] + (["--stat"] if args.stat else [])
        r = git(g, cwd)
        print(r.stdout, end="")
        return r.returncode


if __name__ == "__main__":
    sys.exit(main())
