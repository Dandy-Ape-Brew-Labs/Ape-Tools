# Agent Tools

[![CI](https://github.com/Dandy-Ape-Brew-Labs/Ape-Tools/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Dandy-Ape-Brew-Labs/Ape-Tools/actions/workflows/ci.yml)

A collection of standalone scripts and tools designed to be invoked by AI
agents (and humans). Tools may be written in any language — Python, Node.js,
Go, Bash — as long as they follow the conventions below.

## Layout

```text
tools/
  <tool-name>/
    tool.json        # required: machine-readable manifest
    <entrypoint>     # the script itself
    README.md        # human-facing docs
lib/                 # shared Python helpers (agentlib)
tests/               # per-tool smoke tests: tests/<name>/smoke.sh
package.json         # shared Node dependencies (all tools)
pyproject.toml       # shared Python dependencies (uv)
vendor/              # downloaded binaries, gitignored (see tools/*/install.sh)
install.sh           # installer — in-place setup or lean copy to a prefix
SKILL.md             # agent-facing install/use skill
AGENTS.md            # instructions for AI agents using this repo
```

Persistent tool state (todos, memory, question queue, process
registry, outbox, secrets vault, knowledge/RAG stores, search indexes,
docset cache, trash) lives under `~/.local/share/agent-tools/`;
override with `AGENT_TOOLS_HOME`.

## Install

```sh
# one-liner — fetches the repo and installs a lean payload (default ~/.local/opt/ape-tools)
curl -fsSL https://raw.githubusercontent.com/Dandy-Ape-Brew-Labs/Ape-Tools/main/install.sh | bash

# or: the clone IS the install
git clone https://github.com/Dandy-Ape-Brew-Labs/Ape-Tools.git ~/.local/opt/ape-tools
~/.local/opt/ape-tools/install.sh
```

The payload is deliberately small — `tools/`, `lib/`, lockfiles, docs —
so an installed copy contains runnable tools, not test fixtures and dev
files. It generates `bin/ape`, a dispatcher that runs any tool from any
directory (picks `python3`/`uv run`/`node` per manifest):

```sh
~/.local/opt/ape-tools/bin/ape file-read /etc/hosts --head 5
~/.local/opt/ape-tools/bin/ape list-tools --format index
```

Flags: `--prefix DIR`, `--tools a,b` (subset), `--update`, `--no-deps`,
`--no-node`, `--obscura`, `--with-tests`. The toolbox can also install
itself: `ape install --prefix DIR`.

### Tell your agent to install it

Paste this to any capable AI agent:

```text
Install the Ape Tools agent toolbox: run
curl -fsSL https://raw.githubusercontent.com/Dandy-Ape-Brew-Labs/Ape-Tools/main/install.sh | bash
(or clone https://github.com/Dandy-Ape-Brew-Labs/Ape-Tools to
~/.local/opt/ape-tools and run its install.sh). Afterwards invoke tools
via ~/.local/opt/ape-tools/bin/ape <tool> [args], and read AGENTS.md in
the install for the tool contract. Optionally register its MCP server:
uv run --project ~/.local/opt/ape-tools ~/.local/opt/ape-tools/tools/mcp-serve/mcp_serve.py
```

The root `SKILL.md` encodes the same procedure for skill-loading agents.

## Development setup

```sh
uv sync                            # Python environment (creates .venv)
npm install                        # Node dependencies
tools/obscura-browse/install.sh    # Obscura browser binary -> vendor/obscura/
python3 tools/secrets/secrets.py check   # which env vars each tool needs vs has
```

## Discovering and running tools

Each tool declares a `tool.json` manifest with its `run` command, arguments,
environment variables, and dependencies. Three discovery layers:

```sh
# 1. Compact index — one line per tool, cheap to always include in context
python3 tools/list-tools/list_tools.py --format index

# 2. Intent search — describe the task, get ranked tools + manifests
python3 tools/tool-search/search.py "edit a file in place"
python3 tools/tool-search/search.py "select:file-edit"   # exact lookup

# 3. Full catalogue — every manifest, for bootstrapping
python3 tools/list-tools/list_tools.py --format json --full
```

Run a tool using the `run` command from its manifest, e.g.:

```sh
python3 tools/file-edit/file_edit.py --file x.py --old "a" --new "b"
node tools/obscura-browse/browse.js https://example.com
```

### MCP server

`tools/mcp-serve/` exposes every manifest over MCP stdio — point any
MCP client at it to get the whole toolbox:

```sh
claude mcp add agent-tools -- uv run "$PWD/tools/mcp-serve/mcp_serve.py"
```

`mcp-serve` wraps tools as one-shot subprocess calls, so it excludes
`web-browser-mcp` — a standalone MCP server for stateful stealth-browser
control that MCP clients should attach directly. To call *other* MCP
servers from a script, use `mcp-call` (config: `$MCP_CONFIG`,
`$AGENT_TOOLS_HOME/mcp.json`, or `./mcp.json`).

## Testing

Every tool may declare `"selftest": "tests/<name>/smoke.sh"` in its
manifest. Run all of them:

```sh
python3 tools/selftest/selftest.py              # manifests + smokes
python3 tools/selftest/selftest.py --only file-edit
python3 tools/selftest/selftest.py --manifests-only
```

Smoke tests must be non-interactive and deterministic — use temp
dirs (`$TEST_TMPDIR` via `tests/lib.sh`) and skip gracefully when an
optional dependency (display, daemon, network) is missing.

## Adding a new tool

1. Create `tools/<tool-name>/`.
2. Add the script(s). Put secrets/config in environment variables — never
   hardcode credentials.
3. Add a `tool.json` manifest (see `tools/list-tools/tool.json` for the
   required fields; `use_when`, `category`, `keywords` are recommended —
   they feed `tool-search`).
4. Add a `README.md` documenting prerequisites, usage, and output.
5. Add a smoke test at `tests/<name>/smoke.sh` and declare it via the
   manifest's `selftest` field.
6. Add shared dependencies with `uv add <pkg>` (Python) or
   `npm install <pkg> --save-exact` (Node). Only give a tool its own
   `pyproject.toml`/`package.json`/`go.mod` when it needs isolated or
   conflicting dependencies.

## Conventions

- **stdout** carries the result; diagnostics go to **stderr**.
- Exit `0` on success, non-zero on failure.
- Config comes from the environment or CLI args — never interactive prompts
  (agents can't answer them) and never hardcoded secrets.
- Tools must be runnable from the repo root using the `run` field.

## Contributing

`main` is protected — no direct pushes. Open a pull request from a
feature branch (`gh pr create`); a ruleset enforces PRs for everyone.
Run `python3 tools/selftest/selftest.py` before opening the PR.
