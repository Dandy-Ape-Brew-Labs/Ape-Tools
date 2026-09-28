#!/usr/bin/env python3
"""Run available linters over the repo and emit a normalized JSON report.

Output contract (stdout only):
  {"linters": [{"name", "status": pass|fail|skipped|error,
                "total": int, "findings": [{file, line, col, level, code,
                message}], "error"?: str}]}

This script NEVER fails the build: a missing binary yields status 'skipped',
lint findings yield 'fail', and the process always exits 0. Lint is advisory.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(argv: list[str]) -> tuple[int | None, str, str]:
    try:
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                              timeout=300)
        return proc.returncode, proc.stdout, proc.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return None, "", str(exc)


def skipped(name: str, why: str) -> dict:
    return {"name": name, "status": "skipped", "total": 0,
            "findings": [], "error": why}


def rel(path: str | None) -> str | None:
    """Make an absolute path repo-relative for tidy reports."""
    if not path:
        return path
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return path


def lint_ruff() -> dict:
    if shutil.which("ruff"):
        cmd = ["ruff"]
    elif shutil.which("uvx"):
        cmd = ["uvx", "ruff@0.14.0"]
    else:
        return skipped("ruff (python)", "neither ruff nor uvx on PATH")
    rc, out, err = run([*cmd, "check", "--output-format", "json",
                        "tools", "lib", "tests", ".github/ci"])
    if rc is None:
        return skipped("ruff (python)", f"ruff failed to launch: {err}")
    try:
        items = json.loads(out or "[]")
    except json.JSONDecodeError:
        return {"name": "ruff (python)", "status": "error", "total": 0,
                "findings": [], "error": (err or out)[-2000:]}
    findings = [
        {
            "file": rel(it.get("filename")),
            "line": (it.get("location") or {}).get("row"),
            "col": (it.get("location") or {}).get("column"),
            "level": "error" if (it.get("code") or "").startswith("E9")
                     else "warning",
            "code": it.get("code") or "",
            "message": it.get("message", ""),
        }
        for it in items
    ]
    return {"name": "ruff (python)", "status": "fail" if findings else "pass",
            "total": len(findings), "findings": findings}


def lint_shellcheck() -> dict:
    if not shutil.which("shellcheck"):
        return skipped("shellcheck (bash)", "shellcheck not on PATH")
    files = sorted(str(p) for p in ROOT.glob("tests/**/*.sh")) + ["install.sh"]
    rc, out, err = run(["shellcheck", "-f", "json", *files])
    if rc is None:
        return skipped("shellcheck (bash)", f"shellcheck failed to launch: {err}")
    try:
        parsed = json.loads(out or "[]")
        # shellcheck >=0.9 emits {"comments": [...]}, older emits a bare list
        comments = parsed.get("comments", []) if isinstance(parsed, dict) else parsed
    except json.JSONDecodeError:
        return {"name": "shellcheck (bash)", "status": "error", "total": 0,
                "findings": [], "error": (err or out)[-2000:]}
    findings = [
        {
            "file": rel(c.get("file")),
            "line": c.get("line"),
            "col": c.get("column"),
            "level": c.get("level", "info"),
            "code": f"SC{c.get('code')}" if c.get("code") else "",
            "message": c.get("message", ""),
        }
        for c in comments
    ]
    return {"name": "shellcheck (bash)",
            "status": "fail" if findings else "pass",
            "total": len(findings), "findings": findings}


def lint_node() -> dict:
    if not shutil.which("node"):
        return skipped("node --check (js syntax)", "node not on PATH")
    js_files = sorted(
        str(p) for p in (*ROOT.glob("tools/**/*.js"), *ROOT.glob("tests/**/*.js"))
    )
    findings = []
    for f in js_files:
        rc, _, err = run(["node", "--check", f])
        if rc:
            first = next((ln for ln in err.splitlines() if ln.strip()),
                         "syntax error")
            findings.append({"file": rel(f), "line": None, "col": None,
                             "level": "error", "code": "",
                             "message": first.strip()})
    return {"name": "node --check (js syntax)",
            "status": "fail" if findings else "pass",
            "total": len(findings), "findings": findings}


def main() -> int:
    report = {"linters": [lint_ruff(), lint_shellcheck(), lint_node()]}
    for entry in report["linters"]:
        print(f"[lint] {entry['name']}: {entry['status']} "
              f"({entry['total']} findings)", file=sys.stderr)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
