"""Expose the whole toolbox as an MCP server (stdio transport).

Each tools/<name>/ manifest becomes an MCP tool taking a free-form
`args` string (shlex-split) matching that tool's CLI grammar — the
same contract `run` documents, so agents reuse what tool-search
returned.

Run:  uv run tools/mcp-serve/mcp_serve.py
Claude Code:  claude mcp add agent-tools -- uv run .../mcp_serve.py
"""

import importlib.util
import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

list_tools = _load("list_tools",
                   REPO_ROOT / "tools/list-tools/list_tools.py")

# mcp-serve itself, plus tools that ARE MCP servers — wrapping them as
# one-shot subprocess calls would hang until timeout.
EXPOSED_EXCLUDE = {"mcp-serve", "web-browser-mcp"}
TIMEOUT = int(os.environ.get("AGENT_TOOLS_MCP_TIMEOUT", "120"))


def argv_for(manifest: dict, args: str, cwd: str | None) -> list[str]:
    script = REPO_ROOT / "tools" / manifest["dir"] / manifest["entrypoint"]
    lang = manifest.get("language", "python")
    exe = "node" if lang in ("node", "javascript") else "python3"
    argv = [exe, str(script)]
    if cwd:
        argv += ["--cwd", cwd]
    argv += shlex.split(args)
    return argv


def run_tool(manifest: dict, args: str, cwd: str | None) -> str:
    try:
        proc = subprocess.run(
            argv_for(manifest, args, cwd),
            cwd=cwd or str(REPO_ROOT),
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"error: timed out after {TIMEOUT}s"
    out = proc.stdout
    if proc.returncode != 0:
        out += f"\n[exit {proc.returncode}] {proc.stderr.strip()}"
    return out or "(no output)"


def build_server():
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("agent-tools",
                     instructions="Standalone agent toolbox. Each tool "
                     "takes an `args` string matching its CLI grammar "
                     "(see manifest `run`/`args` fields or README).")
    for m in list_tools.load_manifests(validate=False):
        if m["name"] in EXPOSED_EXCLUDE or "entrypoint" not in m:
            continue
        doc = m["description"]
        if m.get("args"):
            doc += "\n\nArgs:\n" + "\n".join(
                f"  {a['name']}: {a.get('description','')}"
                for a in m["args"])

        def make_fn(man: dict):
            def invoke(args: str = "", cwd: str = "") -> str:
                return run_tool(man, args, cwd or None)
            invoke.__name__ = man["name"].replace("-", "_")
            invoke.__doc__ = doc
            return invoke

        server.add_tool(make_fn(m), name=m["name"],
                        description=doc.split("\n")[0][:1024])
    return server


def main() -> int:
    build_server().run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
