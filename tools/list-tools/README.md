# list-tools

Enumerates every tool in this repository by scanning `tools/*/tool.json`.
Stdlib-only, so it runs with any Python >= 3.11 — no install step required.

## Usage

```sh
python3 tools/list-tools/list_tools.py              # human-readable table
python3 tools/list-tools/list_tools.py --format json # machine-readable
python3 tools/list-tools/list_tools.py --full        # include args/env/deps
```

Manifests with invalid JSON or missing required fields (`name`, `description`,
`language`, `run`) are reported on stderr and skipped.
