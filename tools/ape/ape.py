#!/usr/bin/env python3
"""ape — one entry point for the whole toolbox: `ape <tool> [args...]`.

Resolves the tool's manifest (tools/<name>/tool.json), picks the right
interpreter from `language` + `dependencies`, and execs the entrypoint.
Works from any cwd — paths resolve against the install root, not the
caller's directory.

  ape file-read /etc/hosts --head 5
  ape list-tools --format index
  ape --list            # same as `ape list-tools --format index`
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"


def die(msg: str, code: int = 1) -> "NoReturn":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def find_manifest(name: str) -> Path | None:
    direct = TOOLS_DIR / name / "tool.json"
    if direct.is_file():
        return direct
    for candidate in sorted(TOOLS_DIR.glob("*/tool.json")):
        try:
            if json.loads(candidate.read_text(encoding="utf-8")).get("name") == name:
                return candidate
        except json.JSONDecodeError:
            continue
    return None


def argv_for(manifest: dict, entrypoint: Path, rest: list[str]) -> list[str]:
    lang = manifest.get("language", "python")
    if lang in ("node", "javascript"):
        return ["node", str(entrypoint), *rest]
    if lang in ("bash", "shell", "sh"):
        return ["bash", str(entrypoint), *rest]
    if manifest.get("dependencies"):
        # Shared venv from uv sync; --project pins it regardless of cwd.
        return ["uv", "run", "--project", str(ROOT), str(entrypoint), *rest]
    return ["python3", str(entrypoint), *rest]


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        sys.stderr.write(__doc__)
        return 2 if not args else 0

    if args[0] == "--list":
        args = ["list-tools", "--format", "index"]

    name, rest = args[0], args[1:]
    manifest_path = find_manifest(name)
    if manifest_path is None:
        die(f"no tool '{name}' — try: ape --list", 2)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest.get("entrypoint")
    if not entry:
        die(f"tool '{name}' has no entrypoint in its manifest", 2)
    entrypoint = manifest_path.parent / entry
    if not entrypoint.is_file():
        die(f"entrypoint missing: {entrypoint}", 1)

    argv = argv_for(manifest, entrypoint, rest)
    try:
        os.execvpe(argv[0], argv, os.environ)
    except FileNotFoundError:
        die(f"interpreter not found: '{argv[0]}' — install it and retry", 127)
    return 127  # unreachable


if __name__ == "__main__":
    sys.exit(main())
