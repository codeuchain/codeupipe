"""Echo MCP Server — example docked sub-server.

A minimal MCP server that echoes messages back.
This demonstrates how to create a server that docks into the hub.

Run standalone: python -m codeupipe.ai.servers.echo
"""

from mcp.server.fastmcp import FastMCP

server = FastMCP("echo")


@server.tool()
async def echo_message(message: str) -> str:
    """Echo a message back to the caller."""
    return f"Echo: {message}"


@server.tool()
async def echo_reverse(message: str) -> str:
    """Echo a message back in reverse."""
    return f"Echo: {message[::-1]}"


@server.tool()
async def echo_upper(message: str) -> str:
    """Echo a message back in uppercase."""
    return f"Echo: {message.upper()}"


if __name__ == "__main__":
    server.run(transport="stdio")
