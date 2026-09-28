"""GitHub operations via the authenticated `gh` CLI — the reference
external-service connector. Passes results through as JSON.

  github.py auth                     # who am I
  github.py api <endpoint> [--method GET] [--field k=v]
  github.py pr list [--repo o/r] [--state open] [--limit 20]
  github.py pr view <num> [--repo o/r]
  github.py pr create --title T --body B [--base main] [--head B]
  github.py issue list|view|create ...
  github.py repo view [--repo o/r]
  github.py search <query> [--type code|issues|repos]
  github.py run -- <raw gh args>     # escape hatch

Requires `gh auth login` beforehand — fails fast otherwise.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def require_gh() -> None:
    if not shutil.which("gh"):
        agentlib.die("gh CLI not installed", 2)
    r = gh(["auth", "status"])
    if r.returncode != 0:
        agentlib.die("gh not authenticated — run 'gh auth login'", 3)


def emit_gh_json(r: subprocess.CompletedProcess) -> int:
    if r.returncode != 0:
        agentlib.die(r.stderr.strip() or "gh failed", 1)
    try:
        agentlib.emit(json.loads(r.stdout))
    except json.JSONDecodeError:
        print(r.stdout, end="")
    return 0


def repo_flag(args) -> list[str]:
    return ["--repo", args.repo] if getattr(args, "repo", None) else []


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth")

    a = sub.add_parser("api"); a.add_argument("endpoint")
    a.add_argument("--method", default="GET")
    a.add_argument("--field", action="append", default=[],
                   help="k=v, repeatable")

    for obj in ("pr", "issue"):
        s = sub.add_parser(obj)
        s.add_argument("op", choices=["list", "view", "create", "close", "merge"]
                       if obj == "pr" else ["list", "view", "create", "close"])
        s.add_argument("num", nargs="?", type=int)
        s.add_argument("--repo"); s.add_argument("--state", default=None)
        s.add_argument("--limit", type=int, default=20)
        s.add_argument("--title"); s.add_argument("--body")
        s.add_argument("--base"); s.add_argument("--head")

    rv = sub.add_parser("repo"); rv.add_argument("op", choices=["view"])
    rv.add_argument("--repo")

    se = sub.add_parser("search"); se.add_argument("query")
    se.add_argument("--type", dest="kind", default="code",
                    choices=["code", "issues", "repos", "commits"])
    se.add_argument("--limit", type=int, default=10)

    rn = sub.add_parser("run"); rn.add_argument("gh_args", nargs="*")
    args = p.parse_args()

    require_gh()

    if args.cmd == "auth":
        r = gh(["api", "user", "--jq",
                '{login: .login, name: .name}'])
        return emit_gh_json(r)

    if args.cmd == "api":
        g = ["api", args.endpoint, "--method", args.method]
        for f in args.field:
            k, _, v = f.partition("=")
            g += ["-f", f"{k}={v}"]
        return emit_gh_json(gh(g))

    if args.cmd in ("pr", "issue"):
        obj = args.cmd
        if args.op == "list":
            g = [obj, "list", "--json",
                 "number,title,state,author,createdAt",
                 "--limit", str(args.limit), *repo_flag(args)]
            if args.state:
                g += ["--state", args.state]
            return emit_gh_json(gh(g))
        if args.op == "view":
            if args.num is None:
                agentlib.die("view needs <num>", 2)
            fields = ("number,title,state,author,body,url,headRefName"
                      if obj == "pr" else
                      "number,title,state,author,body,url")
            g = [obj, "view", str(args.num), "--json", fields,
                 *repo_flag(args)]
            return emit_gh_json(gh(g))
        if args.op == "create":
            if not args.title:
                agentlib.die("create needs --title", 2)
            g = [obj, "create", "--title", args.title,
                 "--body", args.body or "", *repo_flag(args)]
            if obj == "pr":
                if args.base:
                    g += ["--base", args.base]
                if args.head:
                    g += ["--head", args.head]
            return emit_gh_json(gh(g))
        if args.op in ("close", "merge"):
            if args.num is None:
                agentlib.die(f"{args.op} needs <num>", 2)
            if args.op == "merge" and obj != "pr":
                agentlib.die("merge only applies to pr", 2)
            g = [obj, args.op, str(args.num), *repo_flag(args)]
            return emit_gh_json(gh(g))

    if args.cmd == "repo":
        g = ["repo", "view", "--json",
             "name,owner,description,defaultBranchRef,url,isPrivate",
             *repo_flag(args)]
        return emit_gh_json(gh(g))

    if args.cmd == "search":
        g = ["search", args.kind, args.query,
             "--limit", str(args.limit)]
        if args.kind != "code":
            g += ["--json", "repository,title,url,state"
                  if args.kind == "issues" else
                  "fullName,description,stargazersCount,url"
                  if args.kind == "repos" else
                  "sha,commit,repository"]
        else:
            g += ["--json", "repository,path,url"]
        return emit_gh_json(gh(g))

    if args.cmd == "run":
        if not args.gh_args:
            agentlib.die("run needs gh args (e.g. run -- pr checks 5)", 2)
        gargv = [a for a in args.gh_args if a != "--"]
        return emit_gh_json(gh(gargv))


if __name__ == "__main__":
    sys.exit(main())
