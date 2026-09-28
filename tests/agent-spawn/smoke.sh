#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

out=$(python3 "$REPO_ROOT/tools/agent-spawn/agent_spawn.py" backends)
assert_contains '"claude"' "$out"
assert_contains '"gemini"' "$out"

# don't actually spawn an LLM in tests (cost/latency); verify arg
# plumbing with a deliberately-missing backend
if python3 "$REPO_ROOT/tools/agent-spawn/agent_spawn.py" run "hi" --backend nonexistent 2>/dev/null; then
  fail "expected failure for missing backend"
fi
