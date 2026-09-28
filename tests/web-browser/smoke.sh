#!/usr/bin/env bash
# web-browser smoke: syntax-check entry points and validate scenarios.json.
# No LM Studio or browser needed. Full E2E: node tests/web-browser/e2e.js
source "$(dirname "$0")/../lib.sh"

node --check "$REPO_ROOT/tools/web-browser/agent.js"
node --check "$REPO_ROOT/tests/web-browser/e2e.js"
python3 -c "import json; json.load(open('$REPO_ROOT/tests/web-browser/scenarios.json'))"

echo "web-browser OK"
