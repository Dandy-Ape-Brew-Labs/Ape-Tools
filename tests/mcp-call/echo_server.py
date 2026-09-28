"""Minimal stdio MCP server for the mcp-call smoke test."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo")


@mcp.tool()
def echo(text: str) -> str:
    return f"echo:{text}"


@mcp.resource("memo://hello")
def hello() -> str:
    return "hello world"


if __name__ == "__main__":
    mcp.run()
