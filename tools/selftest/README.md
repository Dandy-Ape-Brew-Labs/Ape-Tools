# selftest

The catalogue gate. Validates every `tools/*/tool.json` manifest and runs
each tool's declared smoke test.

## Usage

```sh
python3 tools/selftest/selftest.py                 # everything
python3 tools/selftest/selftest.py --only file-read
python3 tools/selftest/selftest.py --manifests-only
```

## Test convention

Tests live in the root `tests/` directory, outside tool code:

```
tests/
  <tool-name>/smoke.sh     # executable scenario; exit 0 = pass
  fixtures/                # shared input data
```

A tool opts in by adding `"selftest": "tests/<name>/smoke.sh"` to its
manifest. During smokes, `AGENT_TOOLS_HOME` points at a fresh temp dir,
`TEST_TMPDIR` is a scratch directory, and `REPO_ROOT` is the repo root.
