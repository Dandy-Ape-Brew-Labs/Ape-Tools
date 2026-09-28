"""Enumerate agent tools by scanning tools/*/tool.json manifests.

Output modes:
  table  — human-readable list (default)
  json   — machine-readable manifests
  index  — one line per tool: "name — use_when" (the Tier-1 catalogue index)
"""

import argparse
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
REQUIRED_FIELDS = ("name", "description", "language", "run")
RECOMMENDED_FIELDS = ("use_when", "category")
CATEGORIES = {
    "files", "search", "exec", "web", "gui", "state", "code", "git",
    "interact", "orchestrate", "integrate", "util", "meta", "security",
}


def load_manifests(validate: bool = True) -> list[dict]:
    manifests: list[dict] = []
    for manifest_path in sorted(TOOLS_DIR.glob("*/tool.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"error: {manifest_path}: invalid JSON: {exc}", file=sys.stderr)
            continue
        missing = [field for field in REQUIRED_FIELDS if field not in manifest]
        if missing:
            print(
                f"error: {manifest_path}: missing fields {missing}",
                file=sys.stderr,
            )
            continue
        if validate:
            for field in RECOMMENDED_FIELDS:
                if field not in manifest:
                    print(
                        f"warn: {manifest_path}: missing recommended field '{field}'",
                        file=sys.stderr,
                    )
            cat = manifest.get("category")
            if cat is not None and cat not in CATEGORIES:
                print(
                    f"warn: {manifest_path}: unknown category '{cat}'",
                    file=sys.stderr,
                )
            use_when = manifest.get("use_when")
            if use_when and len(use_when.split()) > 15:
                print(
                    f"warn: {manifest_path}: use_when should be ~12 words",
                    file=sys.stderr,
                )
            entry = manifest.get("entrypoint")
            if entry and not (manifest_path.parent / entry).exists():
                print(
                    f"error: {manifest_path}: entrypoint '{entry}' not found",
                    file=sys.stderr,
                )
                continue
        manifest["dir"] = manifest_path.parent.name
        manifests.append(manifest)
    return manifests


def print_index(manifests: list[dict]) -> None:
    for m in manifests:
        use_when = m.get("use_when") or m["description"].split(".")[0]
        print(f"{m['name']} — {use_when}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format", choices=("table", "json", "index"), default="table"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="include args, env vars, and dependency details",
    )
    args = parser.parse_args()

    manifests = load_manifests()

    if args.format == "index":
        print_index(manifests)
        return 0

    if args.format == "json":
        output = manifests if args.full else [
            {
                "name": m["name"],
                "description": m["description"],
                "language": m["language"],
                "run": m["run"],
            }
            for m in manifests
        ]
        print(json.dumps(output, indent=2))
        return 0

    for manifest in manifests:
        print(f"{manifest['name']} [{manifest['language']}]")
        print(f"  {manifest['description']}")
        print(f"  run: {manifest['run']}")
        if args.full:
            for arg in manifest.get("args", []):
                default = arg.get("default")
                req = "required" if arg.get("required") else f"default: {default}"
                print(f"    arg {arg['name']} ({req}): {arg.get('description', '')}")
            for key, desc in manifest.get("env", {}).items():
                print(f"    env {key}: {desc}")
            if manifest.get("dependencies"):
                print(f"    deps: {', '.join(manifest['dependencies'])}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
