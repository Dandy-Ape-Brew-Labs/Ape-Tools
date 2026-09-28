"""Locate and load agent skills (*/SKILL.md packages) — read-only.

  skill_load.py list                 # every discovered skill + metadata
  skill_load.py list --roots ~/skills .devin/skills
  skill_load.py get playwright       # frontmatter + full SKILL.md text

Default roots (first-found wins on name collisions):
  ./.devin/skills ./.claude/skills ./.agents/skills ./skills
  ~/.agents/skills ~/.claude/skills ~/.config/devin/skills

Frontmatter is parsed leniently (--- delimited, key: value) — no
YAML dependency. 'get' returns the skill path so callers can also
glob sibling resource files (scripts, references).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

HOME = Path.home()


def default_roots() -> list[Path]:
    cwd = Path.cwd()
    return [
        cwd / ".devin" / "skills", cwd / ".claude" / "skills",
        cwd / ".agents" / "skills", cwd / "skills",
        HOME / ".agents" / "skills", HOME / ".claude" / "skills",
        HOME / ".config" / "devin" / "skills",
    ]


def parse_frontmatter(text: str) -> dict:
    meta = {}
    if not text.startswith("---"):
        return meta
    end = text.find("\n---", 3)
    if end == -1:
        return meta
    for line in text[3:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip("\"'")
    return meta


def scan(roots: list[Path]) -> list[dict]:
    found, seen = [], set()
    for root in roots:
        root = root.expanduser()
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            name = skill_md.parent.name
            if name in seen:
                continue
            seen.add(name)
            try:
                text = skill_md.read_text(errors="replace")
            except OSError:
                continue
            meta = parse_frontmatter(text)
            found.append({
                "name": meta.get("name", name),
                "dir": name,
                "path": str(skill_md),
                "root": str(root),
                "description": meta.get("description"),
                "metadata": meta})
    return found


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("list")
    l.add_argument("--roots", nargs="*", default=None)
    g = sub.add_parser("get")
    g.add_argument("name")
    g.add_argument("--roots", nargs="*", default=None)
    args = p.parse_args()

    roots = [Path(r) for r in args.roots] if args.roots else default_roots()
    skills = scan(roots)

    if args.cmd == "list":
        agentlib.emit(skills)
        return 0

    if args.cmd == "get":
        for s in skills:
            if s["name"] == args.name or s["dir"] == args.name:
                content = Path(s["path"]).read_text(errors="replace")
                agentlib.emit({**s, "content": content})
                return 0
        agentlib.die(
            f"skill '{args.name}' not found — "
            f"available: {[s['name'] for s in skills][:20]}", 1)


if __name__ == "__main__":
    sys.exit(main())
