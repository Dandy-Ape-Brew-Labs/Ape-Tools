# mcp-call

Client direction of the MCP bridge (`mcp-serve` exposes this toolbox;
`mcp-call` reaches *out* to other MCP servers). One command = one
ephemeral stdio session.

```sh
mcp_call.py servers
mcp_call.py tools email-server
mcp_call.py call email-server search_threads --args '{"query":"from:boss"}'
mcp_call.py read memo-server memo://notes/today
```

## Config

`$MCP_CONFIG`, else `$AGENT_TOOLS_HOME/mcp.json`, else `./mcp.json`:

```json
{"mcpServers": {"echo": {"command": "uv", "args": ["run", "server.py"],
                         "env": {"KEY": "val"}}}}
```

`env` values are never echoed back — `servers` lists env key names only.
