#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

T="$REPO_ROOT/tools/mcp-call/mcp_call.py"

# config pointing at the fixture echo server
mkdir -p "$AGENT_TOOLS_HOME"
cat > "$AGENT_TOOLS_HOME/mcp.json" <<EOF
{"mcpServers":{"echo":{"command":"uv","args":["run","$REPO_ROOT/tests/mcp-call/echo_server.py"]}}}
EOF

out=$(cd "$REPO_ROOT" && uv run "$T" servers)
assert_contains '"echo"' "$out"

out=$(cd "$REPO_ROOT" && uv run "$T" tools echo)
assert_contains '"echo"' "$out"

out=$(cd "$REPO_ROOT" && uv run "$T" call echo echo --args '{"text":"hi"}')
assert_contains 'echo:hi' "$out"

out=$(cd "$REPO_ROOT" && uv run "$T" resources echo)
assert_contains 'memo://hello' "$out"

out=$(cd "$REPO_ROOT" && uv run "$T" read echo memo://hello)
assert_contains 'hello world' "$out"

# unknown server -> exit 2
rc=0
uv run "$T" tools nope >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] || fail "expected exit 2 for unknown server, got $rc"

echo "mcp-call OK"
