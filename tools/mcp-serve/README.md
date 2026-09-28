# mcp-serve

Bridges the toolbox to any MCP-capable agent (Claude Code, Cursor,
etc.) over stdio. Each `tool.json` becomes an MCP tool with a single
`args` string parameter — the same CLI grammar the manifest documents.

```sh
# Claude Code
claude mcp add agent-tools -- uv run "$PWD/tools/mcp-serve/mcp_serve.py"
```

Every call: `invoke(args="...", cwd=".")` → subprocess → stdout
returned as text (stderr appended on failure). Timeout via
`AGENT_TOOLS_MCP_TIMEOUT` (default 120s). `mcp-serve` excludes itself
to avoid recursive invocation.
