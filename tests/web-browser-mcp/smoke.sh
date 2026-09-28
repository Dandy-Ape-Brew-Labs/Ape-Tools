#!/usr/bin/env bash
# web-browser-mcp smoke: syntax-check the server, verify tool registration,
# and run a real MCP stdio handshake (initialize + list_tools + browser_status).
# No browser or LM Studio needed — browser_status only probes the endpoint.
source "$(dirname "$0")/../lib.sh"

SERVER="$REPO_ROOT/tools/web-browser-mcp/server.py"

python3 -m py_compile "$SERVER"
python3 -c "import json; json.load(open('$REPO_ROOT/tools/web-browser-mcp/tool.json'))"

OUT="$(cd "$REPO_ROOT" && uv run "$SERVER" --selfcheck)"
for tool in browser_navigate browser_snapshot browser_look browser_click \
            browser_click_xy browser_type browser_press browser_scroll \
            browser_back browser_eval browser_wait browser_status \
            browser_close browser_browse; do
  assert_contains "$tool" "$OUT"
done

# Live MCP handshake over stdio: initialize, list tools, call browser_status
# (safe without a browser — it only probes the CDP endpoint).
cd "$REPO_ROOT" && uv run python3 - <<'PYEOF'
import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command="uv", args=["run", "tools/web-browser-mcp/server.py"]
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert "browser_navigate" in names, names
            assert "browser_browse" in names, names
            assert len(names) == 14, names
            r = await session.call_tool("browser_status", {})
            assert not r.isError, r.content[0].text
            status = json.loads(r.content[0].text)
            assert "cdp_endpoint" in status, status
            assert "server_reachable" in status, status
            print("handshake OK:", len(names), "tools")

asyncio.run(main())
PYEOF

echo "web-browser-mcp OK"
