# Agent instructions

This repository is a toolbox: a flat collection of standalone scripts meant to
be invoked by AI agents. Each tool lives in `tools/<name>/` and is described by
a machine-readable `tool.json` manifest.

## Discover tools

Tiered discovery — cheapest first:

```sh
# 1. One line per tool (name — when to use). Cheap; keep in context.
python3 tools/list-tools/list_tools.py --format index

# 2. Describe intent; get ranked tools and their manifests.
python3 tools/tool-search/search.py "edit a file in place"
python3 tools/tool-search/search.py --select file-edit   # exact lookup

# 3. Full validated catalogue.
python3 tools/list-tools/list_tools.py --format json --full
```

Equivalent fallback: glob `tools/*/tool.json` and read the manifests directly.

MCP clients can skip all of this — `uv run tools/mcp-serve/mcp_serve.py`
exposes every tool over stdio (except `web-browser-mcp`, a standalone
stateful MCP server clients attach directly). The other direction —
calling tools/resources on external MCP servers — is `mcp-call`.

## Run tools

Use the `run` field from the manifest verbatim — paths are relative to the
repo root. Fill placeholders from `args` (positional/flag, `required`,
`default`) and set `env` variables when the task requires non-default config.

```sh
node tools/obscura-browse/browse.js https://example.com
CDP_ENDPOINT=ws://127.0.0.1:9223 node tools/obscura-browse/browse.js https://example.com
```

Python tools: `python3` works for stdlib-only tools; use `uv run <script>` when
the tool declares `dependencies` (the shared venv in `.venv` holds them).

In an installed prefix, the `ape` dispatcher handles all of this:
`<prefix>/bin/ape <tool> [args]` runs from any cwd and picks the
interpreter per manifest. `install.sh` (or the `install` tool) produces
a lean payload — no `tests/`, no `.git` — default `~/.local/opt/ape-tools`.

Missing credentials? `python3 tools/secrets/secrets.py check` reports which
env vars every manifest declares and which are actually set.

## Shared state

Stateful tools (plan-todo, memory, ask-user, notify, proc, schedule,
fs-manage trash, send-file, serve, secrets, knowledge, semantic-search,
lib-docs cache, mcp-call config) persist under
`~/.local/share/agent-tools/` — override with `AGENT_TOOLS_HOME`.
`tools/` scripts are stateless; side effects land there. Ask-user uses
file handoff: questions/answers are JSON files a human or another
process writes.

## Test

`tests/<tool>/smoke.sh` per tool, declared via the manifest's `selftest`
field. Helpers (`tests/lib.sh`) provide `TEST_TMPDIR`, `fail`,
`assert_eq`, `assert_contains`, `assert_not_contains`, `assert_file`,
`jqv`. Run everything:

```sh
python3 tools/selftest/selftest.py
```

## Contract every tool follows

- Results on **stdout**, diagnostics on **stderr**. Parse stdout only.
- Exit `0` on success, non-zero on failure (per-manifest `exit_codes`).
- No interactive prompts. Everything is parameterized via args or env vars.
- No hardcoded secrets. Missing credentials fail fast with a stderr message.

## Add a tool

1. `tools/<kebab-case-name>/` containing the script, `tool.json`, `README.md`.
2. Manifest requires `name`, `description`, `language`, `run`; add `args`,
   `env`, `dependencies`, `stdout`, `exit_codes`, `selftest` as applicable.
   Add `use_when` (~12 words), `category`, `keywords` — tool-search ranks
   on them.
3. Add `tests/<name>/smoke.sh` exercising the tool end-to-end; declare it
   as `"selftest": "tests/<name>/smoke.sh"`. Keep it deterministic —
   temp dirs, local fixtures, graceful skips for missing optional deps.
   CI runs the whole suite (`selftest.py --ci`); if a smoke genuinely
   requires a live model, credentials, or a desktop session, set
   `"selftest_ci": false` in the manifest and it is reported as skipped.
4. Shared deps: `uv add <pkg>` for Python, `npm install <pkg> --save-exact` for
   Node. Per-tool manifests only when isolation is genuinely needed.
5. Verify: `python3 tools/selftest/selftest.py --only <name>` passes and
   `list_tools.py --format index` lists the tool without stderr warnings.

## Git workflow

`main` is protected — direct pushes and force-pushes are rejected, and the
branch cannot be deleted. All changes land via pull request:

```sh
git checkout -b <type>/<short-description>   # e.g. feat/clipboard-paste
# commit work, then:
gh pr create --fill
```

A pull_request ruleset with zero required approvals is enforced for everyone
(no admin bypass), so opening a PR is mandatory even though merging is
unblocked. Use `gh pr merge --squash --delete-branch` to keep history linear.
