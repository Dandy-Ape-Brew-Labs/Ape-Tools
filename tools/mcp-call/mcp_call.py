"""Call tools and read resources on other MCP servers over stdio —
the client direction that complements mcp-serve.

  mcp_call.py servers                          # configured servers
  mcp_call.py tools <server>                   # list its tools
  mcp_call.py call <server> <tool> [--args '{"k":1}']
  mcp_call.py resources <server>               # list resources
  mcp_call.py read <server> <uri>              # read a resource

Servers come from $MCP_CONFIG, else $AGENT_TOOLS_HOME/mcp.json, else
./mcp.json — Claude Code shape:
  {"mcpServers": {"name": {"command": "...", "args": [...], "env": {...}}}}

Each invocation spawns an ephemeral stdio session: initialize, run the
operation, shut down. Timeout via $MCP_CALL_TIMEOUT (default 30s).
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from pydantic import AnyUrl

TIMEOUT = float(os.environ.get("MCP_CALL_TIMEOUT", "30"))


def config_path() -> Path:
    if os.environ.get("MCP_CONFIG"):
        return Path(os.environ["MCP_CONFIG"]).expanduser()
    home = Path(os.environ.get(
        "AGENT_TOOLS_HOME", str(agentlib.DEFAULT_STATE))).expanduser() / "mcp.json"
    if home.exists():
        return home
    local = Path("mcp.json")
    return local if local.exists() else home


def load_servers() -> dict:
    path = config_path()
    if not path.exists():
        agentlib.die(
            f"no MCP config at {path} — create it with "
            '{"mcpServers": {"name": {"command": "...", "args": [...]}}}', 2)
    cfg = agentlib.read_json(path)
    servers = (cfg or {}).get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        agentlib.die(f"{path} has no 'mcpServers' entries", 2)
    return servers


def server_params(name: str) -> StdioServerParameters:
    servers = load_servers()
    if name not in servers:
        agentlib.die(f"unknown server '{name}' — "
                     f"configured: {', '.join(sorted(servers))}", 2)
    spec = servers[name]
    if not spec.get("command"):
        agentlib.die(f"server '{name}' has no 'command' in config", 2)
    env = get_default_environment()
    env.update({k: str(v) for k, v in (spec.get("env") or {}).items()})
    return StdioServerParameters(
        command=spec["command"],
        args=[str(a) for a in spec.get("args", [])],
        env=env)


def block(obj) -> dict:
    """Serialize an MCP content block to plain JSON."""
    t = getattr(obj, "type", None)
    if t == "text":
        return {"type": "text", "text": obj.text}
    if t == "image":
        return {"type": "image", "mimeType": obj.mimeType,
                "bytes": len(obj.data)}
    if t == "resource":
        r = obj.resource
        out = {"type": "resource", "uri": str(r.uri)}
        if getattr(r, "text", None) is not None:
            out["text"] = r.text
        return out
    # TextResourceContents / BlobResourceContents (read_resource results)
    if getattr(obj, "text", None) is not None:
        out = {"type": "text", "text": obj.text}
        if getattr(obj, "uri", None) is not None:
            out["uri"] = str(obj.uri)
        return out
    if getattr(obj, "blob", None) is not None:
        out = {"type": "blob", "bytes": len(obj.blob)}
        if getattr(obj, "uri", None) is not None:
            out["uri"] = str(obj.uri)
        if getattr(obj, "mimeType", None) is not None:
            out["mimeType"] = obj.mimeType
        return out
    return {"type": str(t), "repr": repr(obj)[:200]}


async def run_op(name: str, op):
    params = server_params(name)
    async with asyncio.timeout(TIMEOUT):
        async with stdio_client(params) as (rd, wr):
            async with ClientSession(rd, wr) as session:
                await session.initialize()
                return await op(session)


def run(name: str, op):
    try:
        return asyncio.run(run_op(name, op))
    except TimeoutError:
        agentlib.die(f"server '{name}' timed out after {TIMEOUT}s", 1)
    except Exception as exc:
        agentlib.die(f"server '{name}' failed: {exc}", 1)


async def op_list_tools(session):
    res = await session.list_tools()
    return [{"name": t.name,
             "description": getattr(t, "description", None),
             "inputSchema": getattr(t, "inputSchema", None)}
            for t in res.tools]


async def op_list_resources(session):
    res = await session.list_resources()
    return [{"uri": str(r.uri), "name": r.name,
             "description": getattr(r, "description", None),
             "mimeType": getattr(r, "mimeType", None)}
            for r in res.resources]


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("servers")
    t = sub.add_parser("tools"); t.add_argument("server")
    c = sub.add_parser("call")
    c.add_argument("server"); c.add_argument("tool")
    c.add_argument("--args", default="{}",
                   help="JSON object of tool arguments")
    r = sub.add_parser("resources"); r.add_argument("server")
    rd = sub.add_parser("read")
    rd.add_argument("server"); rd.add_argument("uri")
    args = p.parse_args()

    if args.cmd == "servers":
        out = [{"name": name,
                "command": spec.get("command"),
                "args": spec.get("args", []),
                "env_keys": sorted((spec.get("env") or {}).keys())}
               for name, spec in sorted(load_servers().items())]
        agentlib.emit(out)
        return 0

    if args.cmd == "tools":
        agentlib.emit(run(args.server, op_list_tools))
        return 0

    if args.cmd == "resources":
        agentlib.emit(run(args.server, op_list_resources))
        return 0

    if args.cmd == "read":
        async def _read(session):
            res = await session.read_resource(AnyUrl(args.uri))
            return {"contents": [block(b) for b in res.contents]}
        agentlib.emit(run(args.server, _read))
        return 0

    if args.cmd == "call":
        try:
            call_args = json.loads(args.args)
        except json.JSONDecodeError as exc:
            agentlib.die(f"--args is not valid JSON: {exc}", 2)
        if not isinstance(call_args, dict):
            agentlib.die("--args must be a JSON object", 2)

        async def _call(session):
            res = await session.call_tool(args.tool, call_args)
            out = {"isError": bool(res.isError),
                   "content": [block(b) for b in res.content]}
            sc = getattr(res, "structuredContent", None)
            if sc is not None:
                out["structuredContent"] = sc
            return out
        agentlib.emit(run(args.server, _call))
        return 0


if __name__ == "__main__":
    sys.exit(main())
