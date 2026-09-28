#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"

# JSON-RPC handshake: initialize -> tools/list, expect >30 tools
out=$( (printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}'; sleep 2; printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized"}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'; sleep 3) | timeout 20 uv run "$REPO_ROOT/tools/mcp-serve/mcp_serve.py" 2>/dev/null )

count=$(echo "$out" | python3 -c "
import json,sys
for line in sys.stdin:
    line=line.strip()
    if line.startswith('{'):
        d=json.loads(line)
        if d.get('id')==2:
            print(len(d['result']['tools']))
            break
")
[ "${count:-0}" -gt 30 ] || fail "expected >30 MCP tools, got ${count:-none}"
printf '%s MCP tools exposed\n' "$count"
