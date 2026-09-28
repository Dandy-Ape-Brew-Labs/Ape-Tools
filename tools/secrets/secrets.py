"""Secret presence + vault — never prints values.

  secrets.py check                 # which declared env vars are set/missing
  secrets.py list                  # vault names only
  secrets.py set OPENAI_API_KEY    # reads value from stdin (never argv)
  secrets.py del OPENAI_API_KEY
  secrets.py run -- env            # exec cmd with vault vars injected

Vault: $AGENT_TOOLS_HOME/secrets.json (chmod 600). 'run' is the safe
way to use a stored secret — the value enters the child's environment
and never touches stdout, argv, or a file path. 'check' scans every
tool.json env field so missing credentials are visible up front.
"""

import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

REPO = Path(__file__).resolve().parents[2]


def vault_path() -> Path:
    return agentlib.state_file("secrets.json")


def load_vault() -> dict:
    p = vault_path()
    if not p.exists():
        return {}
    mode = p.stat().st_mode
    if mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH):
        print(f"warning: {p} is readable by others — chmod 600",
              file=sys.stderr)
    return agentlib.read_json(p, {})


def save_vault(v: dict) -> None:
    p = vault_path()
    agentlib.write_json(p, v)
    os.chmod(p, 0o600)


def declared_env() -> dict[str, list[str]]:
    """env var name -> [tools that declare it], across manifests."""
    out: dict[str, list[str]] = {}
    for manifest in sorted(REPO.glob("tools/*/tool.json")):
        data = agentlib.read_json(manifest, {})
        for name in (data.get("env") or {}):
            out.setdefault(name, []).append(manifest.parent.name)
    return out


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check"); sub.add_parser("list")
    s = sub.add_parser("set"); s.add_argument("name")
    d = sub.add_parser("del"); d.add_argument("name")
    r = sub.add_parser("run"); r.add_argument("cmdline", nargs="*")
    args = p.parse_args()
    vault = load_vault()

    if args.cmd == "check":
        names = set(declared_env()) | set(vault)
        out = []
        for name in sorted(names):
            out.append({
                "name": name,
                "declared_by": declared_env().get(name, []),
                "in_env": name in os.environ,
                "in_vault": name in vault})
        agentlib.emit(out)
        return 0

    if args.cmd == "list":
        agentlib.emit(sorted(vault))
        return 0

    if args.cmd == "set":
        if not args.name.replace("_", "").isalnum() or not args.name.isupper():
            agentlib.die("name must look like an env var "
                         "(UPPER_SNAKE_CASE)", 2)
        value = sys.stdin.read().rstrip("\n")
        if not value:
            agentlib.die("empty secret on stdin — refusing to store", 2)
        vault[args.name] = value
        save_vault(vault)
        agentlib.emit({"stored": args.name, "vault": str(vault_path())})
        return 0

    if args.cmd == "del":
        if vault.pop(args.name, None) is None:
            agentlib.die(f"{args.name} not in vault", 1)
        save_vault(vault)
        agentlib.emit({"deleted": args.name})
        return 0

    if args.cmd == "run":
        if not args.cmdline:
            agentlib.die("run needs a command: secrets.py run -- cmd", 2)
        env = {**os.environ, **vault}
        try:
            os.execvpe(args.cmdline[0], args.cmdline, env)
        except FileNotFoundError:
            agentlib.die(f"command not found: {args.cmdline[0]}", 2)


if __name__ == "__main__":
    sys.exit(main())
