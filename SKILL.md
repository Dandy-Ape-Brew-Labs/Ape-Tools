---
name: ape-tools
description: Install and drive the Ape Tools agent toolbox — manifest-described CLI tools for files, search, shell, web, GUI, state, and MCP.
---

# Ape Tools

A standalone toolbox for AI agents. Every tool lives in `tools/<name>/`
with a `tool.json` manifest (run command, args, env vars, exit codes).
Contract: results on stdout, diagnostics on stderr, non-zero exit on
failure, never interactive.

## Install

Needs `git`, `python3`; `uv` and `node`/`npm` for dependency tools.
Default prefix: `~/.local/opt/ape-tools`.

```sh
curl -fsSL https://raw.githubusercontent.com/Dandy-Ape-Brew-Labs/Ape-Tools/main/install.sh | bash
# custom prefix:  ... | bash -s -- --prefix DIR
# or: git clone <repo> <dir> && <dir>/install.sh
```

The payload is lean — `tools/`, `lib/`, lockfiles, docs. No tests, no
`.git`. If the toolbox is already present, `ape install --prefix DIR`
installs a copy elsewhere.

## Use

```sh
<prefix>/bin/ape list-tools --format index   # cheap tool index
<prefix>/bin/ape tool-search "edit a file"   # intent search -> manifests
<prefix>/bin/ape <tool> [args]               # run a tool, any cwd
<prefix>/bin/ape secrets check               # which env vars are missing
```

MCP clients get the whole toolbox over stdio:

```sh
uv run --project <prefix> <prefix>/tools/mcp-serve/mcp_serve.py
```

Tool state (todos, memory, secrets vault, indexes) lives under
`AGENT_TOOLS_HOME` (default `~/.local/share/agent-tools`) — shared across
installs and never inside the prefix.
