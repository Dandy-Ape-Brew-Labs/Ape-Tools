"""Validate every tool manifest and run declared smoke tests.

Two stages:
  1. Manifest validation — required fields, entrypoint exists, `run` path
     resolves, args/env/exit_codes shape, schema-v2 fields present.
  2. Smoke tests — for manifests declaring a `selftest` path under tests/,
     run it in a temp dir with AGENT_TOOLS_HOME isolated.

Usage:
  selftest.py [--only name] [--manifests-only]
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

REPO_ROOT = agentlib.REPO_ROOT
TOOLS_DIR = REPO_ROOT / "tools"
REQUIRED = ("name", "description", "language", "run")
SCHEMA_V2 = ("use_when", "category")


def validate_manifest(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON: {exc}"]

    for field in REQUIRED:
        if field not in m:
            errors.append(f"missing required field '{field}'")
    if errors:
        return errors

    for field in SCHEMA_V2:
        if field not in m:
            print(f"warn: {path}: missing schema-v2 field '{field}'", file=sys.stderr)

    entry = m.get("entrypoint")
    if entry and not (path.parent / entry).is_file():
        errors.append(f"entrypoint '{entry}' does not exist")

    run_cmd = m.get("run", "")
    run_parts = run_cmd.split()
    if len(run_parts) >= 2:
        candidate = REPO_ROOT / run_parts[1]
        if "/" in run_parts[1] and not candidate.exists():
            errors.append(f"run path '{run_parts[1]}' does not exist")

    if m.get("name") != path.parent.name:
        errors.append(f"name '{m.get('name')}' != directory '{path.parent.name}'")

    for i, arg in enumerate(m.get("args", [])):
        if not isinstance(arg, dict) or "name" not in arg:
            errors.append(f"args[{i}] malformed (needs 'name')")

    if not isinstance(m.get("exit_codes", {}), dict):
        errors.append("exit_codes must be an object")

    selftest = m.get("selftest")
    if selftest and not (REPO_ROOT / selftest).exists():
        errors.append(f"selftest '{selftest}' does not exist")

    return errors


def run_smoke(manifest_path: Path, smoke: Path, timeout: int) -> dict:
    env = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="agent-tools-test-") as tmp:
        env["AGENT_TOOLS_HOME"] = str(Path(tmp) / "state")
        env["TEST_TMPDIR"] = tmp
        env["REPO_ROOT"] = str(REPO_ROOT)
        try:
            proc = subprocess.run(
                ["bash", str(smoke)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "tool": manifest_path.parent.name,
                "exit": proc.returncode,
                "stderr": proc.stderr[-2000:] if proc.returncode else "",
            }
        except subprocess.TimeoutExpired:
            return {
                "tool": manifest_path.parent.name,
                "exit": 124,
                "stderr": f"smoke timed out after {timeout}s",
            }


def main() -> int:
    parser = agentlib.arg_parser(__doc__)
    parser.add_argument("--only", help="run just one tool (by dir name)")
    parser.add_argument("--manifests-only", action="store_true",
                        help="validate manifests without running smokes")
    parser.add_argument("--timeout", type=int, default=120,
                        help="per-smoke timeout seconds (default 120)")
    args = parser.parse_args()

    results = {"valid": [], "invalid": [], "smoke_pass": [], "smoke_fail": [], "no_smoke": []}
    paths = sorted(TOOLS_DIR.glob("*/tool.json"))
    if args.only:
        paths = [p for p in paths if p.parent.name == args.only]
        if not paths:
            agentlib.die(f"no tool dir named '{args.only}'", 2)

    for path in paths:
        m = agentlib.read_json(path) or {}
        errors = validate_manifest(path)
        name = path.parent.name
        if errors:
            results["invalid"].append({"tool": name, "errors": errors})
            continue
        results["valid"].append(name)
        if args.manifests_only:
            continue
        selftest = m.get("selftest")
        if not selftest:
            results["no_smoke"].append(name)
            continue
        res = run_smoke(path, REPO_ROOT / selftest, args.timeout)
        (results["smoke_pass"] if res["exit"] == 0 else results["smoke_fail"]).append(res)

    ok = not results["invalid"] and not results["smoke_fail"]
    agentlib.emit({"ok": ok, **results})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
