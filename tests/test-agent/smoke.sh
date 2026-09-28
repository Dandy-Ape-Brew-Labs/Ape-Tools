#!/usr/bin/env bash
# test-agent smoke: syntax + scenario-schema validation, then a --dry-run
# sweep. No LLM calls. Full suite: python3 tests/test-agent/run.py
source "$(dirname "$0")/../lib.sh"

D="$(dirname "$0")"
python3 -m py_compile "$D/agent.py" "$D/run.py" "$D/lib_test.py" "$D/test_harness.py"
python3 -m unittest discover -s "$D" -p test_harness.py
python3 -c "import json; json.load(open('$D/scenarios.json'))"

python3 - <<EOF
import json, sys
sys.path.insert(0, "$D")
import lib_test
manifests = lib_test.load_tool_manifests()
scenarios = json.load(open("$D/scenarios.json"))
ids = [s["id"] for s in scenarios]
assert len(ids) == len(set(ids)), "duplicate scenario ids"
for s in scenarios:
    assert s["mode"] in ("forced", "choice", "e2e"), s["id"]
    assert s.get("prompt"), s["id"]
    exp = s.get("expect", {})
    for t in exp.get("tools", []) + exp.get("tools_any", []) + exp.get("tools_forbidden", []):
        assert t in manifests, f"{s['id']}: unknown tool '{t}'"
covered = {t for s in scenarios for t in
           s.get("expect", {}).get("tools", []) +
           s.get("expect", {}).get("tools_any", [])}
missing = set(manifests) - covered - {"web-agent"}  # web-agent: other agent's
print(f"{len(scenarios)} scenarios, forced coverage: {len(covered)}/{len(manifests)}")
assert not missing, f"no forced scenario for: {sorted(missing)}"
EOF

python3 "$D/run.py" --dry-run >/dev/null
echo "test-agent OK"
