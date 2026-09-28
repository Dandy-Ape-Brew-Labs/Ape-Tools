# install

Install the toolbox to a target prefix. Thin manifest wrapper around the
repo-root `install.sh` — every flag forwards unchanged.

```sh
python3 tools/install/install_tool.py --prefix ~/.local/opt/ape-tools
python3 tools/install/install_tool.py --prefix DIR --tools file-read,web-fetch
python3 tools/install/install_tool.py --prefix DIR --update
python3 tools/install/install_tool.py            # in-place setup
```

## What lands in the prefix

`tools/`, `lib/`, `pyproject.toml`, `uv.lock`, `package.json`,
`package-lock.json`, `README.md`, `AGENTS.md`, `SKILL.md`, `install.sh`,
plus a generated `bin/ape` dispatcher. **No `tests/`, no `.git`, no local
docs** — the installed tree is what an agent sees, so it stays lean.
`--with-tests` opts back in for verification work.

Then: `uv sync --frozen`, `npm ci` (skipped with `--no-deps`/`--no-node`
or when uv/npm are absent — a warning, not a failure), and optionally
`--obscura` to fetch the vendored browser binary.

## Standalone bootstrap

The same script works piped from a bare machine (public repo, no auth):

```sh
curl -fsSL https://raw.githubusercontent.com/Dandy-Ape-Brew-Labs/Ape-Tools/main/install.sh | bash
# custom prefix:
curl -fsSL .../install.sh | bash -s -- --prefix /opt/agent-tools
```

Pipe mode clones the repo to a temp dir, copies the payload, and cleans
up — the prefix never sees `.git` or `tests/`.

## Update

`--update` removes only installer-managed paths (tools/, lib/, bin/,
payload files) and re-copies. State under `AGENT_TOOLS_HOME` is never
touched.
