"""MCP Manager Server — agent-driven hub management.

An MCP server whose tools let the agent manage the hub's server
registry on behalf of the user.  This is the "tool-for-tools" pattern:
the agent can list, add, remove, enable, disable, and inspect docked
MCP servers without human intervention.

Architecture:
    Pure functions (add_server, remove_server, …) do the work.
    The FastMCP ``@server.tool()`` decorators are just transport.
    Tests target the pure-function layer — zero FastMCP dependency.

Run standalone:  python -m codeupipe.ai.servers.mcp_manager
"""

from __future__ import annotations

from typing import Any

from codeupipe.ai.hub.config import ServerConfig
from codeupipe.ai.hub.registry import ServerRegistry


# ── Pure functions (testable without mcp dependency) ──────────────────


def list_servers(registry: ServerRegistry) -> dict[str, Any]:
    """List all docked MCP servers.

    Returns:
        {"servers": [...names], "count": N}
    """
    names = registry.list_servers()
    return {"servers": names, "count": len(names)}


def add_server(
    registry: ServerRegistry,
    *,
    name: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    tools: list[str] | None = None,
    timeout: int = 30000,
) -> dict[str, Any]:
    """Add (or replace) a server in the hub registry.

    Returns:
        {"added": True, "replaced": bool, "name": ..., "command": ...}
    """
    replaced = registry.has(name)

    config = ServerConfig(
        name=name,
        command=command,
        args=args or [],
        env=env or {},
        cwd=cwd,
        tools=tools or ["*"],
        timeout=timeout,
    )
    registry.register(config)

    return {
        "added": True,
        "replaced": replaced,
        "name": name,
        "command": command,
        "args": config.args,
        "tools": config.tools,
    }


def remove_server(
    registry: ServerRegistry,
    *,
    name: str,
) -> dict[str, Any]:
    """Remove a server from the hub registry.

    Returns:
        {"removed": bool, "name": ...}
    """
    if not registry.has(name):
        return {"removed": False, "name": name}

    registry.unregister(name)
    return {"removed": True, "name": name}


def enable_server(
    registry: ServerRegistry,
    *,
    name: str,
) -> dict[str, Any]:
    """Re-enable a disabled server.

    Returns:
        {"enabled": bool, "name": ...}
    """
    ok = registry.enable(name)
    return {"enabled": ok, "name": name}


def disable_server(
    registry: ServerRegistry,
    *,
    name: str,
) -> dict[str, Any]:
    """Disable a server (stays docked but excluded from mcp_configs).

    Returns:
        {"disabled": bool, "name": ...}
    """
    ok = registry.disable(name)
    return {"disabled": ok, "name": name}


def server_status(
    registry: ServerRegistry,
    *,
    name: str,
) -> dict[str, Any]:
    """Get status summary for a single docked server.

    Returns:
        {"found": bool, "name": ..., "command": ..., "tools": [...], "disabled": bool}
    """
    config = registry.get(name)
    if config is None:
        return {"found": False, "name": name}

    tools = registry.tools_for_server(name)
    return {
        "found": True,
        "name": name,
        "command": config.command,
        "args": config.args,
        "tools": tools,
        "disabled": registry.is_disabled(name),
        "timeout": config.timeout,
    }


def get_server_config(
    registry: ServerRegistry,
    *,
    name: str,
) -> dict[str, Any]:
    """Get the full config dict for a docked server.

    Returns:
        {"found": bool, "config": {...}} or {"found": False}
    """
    config = registry.get(name)
    if config is None:
        return {"found": False, "name": name}

    return {
        "found": True,
        "config": {
            "name": config.name,
            "command": config.command,
            "args": list(config.args),
            "env": dict(config.env),
            "cwd": config.cwd,
            "tools": list(config.tools),
            "timeout": config.timeout,
        },
    }


def discover_tools(
    registry: ServerRegistry,
    *,
    name: str,
) -> dict[str, Any]:
    """List all tools mapped to a specific server.

    Returns:
        {"found": bool, "name": ..., "tools": [...tool_names]}
    """
    if not registry.has(name):
        return {"found": False, "name": name, "tools": []}

    tools = registry.tools_for_server(name)
    return {"found": True, "name": name, "tools": tools}


# ── Global registry pointer (set by hub at startup) ──────────────────

_hub_registry: ServerRegistry | None = None


def set_hub_registry(registry: ServerRegistry) -> None:
    """Wire the hub's ServerRegistry so tools can reach it."""
    global _hub_registry
    _hub_registry = registry


def _get_registry() -> ServerRegistry:
    """Get the wired registry or raise."""
    if _hub_registry is None:
        raise RuntimeError(
            "MCP Manager not wired — call set_hub_registry() at startup"
        )
    return _hub_registry


# ── FastMCP server (transport layer) ──────────────────────────────────
#
# The server object and its @tool decorators are only instantiated when
# this module runs as ``__main__`` or when ``mcp`` is importable.
# Tests never touch this section — they call the pure functions above.


def _build_server():  # noqa: C901 — intentionally flat
    """Build and return the FastMCP server instance."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("mcp-manager")

    @server.tool()
    async def mcp_list_servers() -> str:
        """List all MCP servers currently docked in the hub.

        Returns a JSON object with server names and count.
        """
        import json
        result = list_servers(_get_registry())
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_add_server(
        name: str,
        command: str,
        args: str = "",
        env: str = "",
        tools: str = "",
        timeout: int = 30000,
    ) -> str:
        """Add a new MCP server to the hub.

        Args:
            name: Unique server name (e.g. "weather", "database").
            command: Command to launch the server (e.g. "python", "node").
            args: Space-separated arguments (e.g. "-m weather_server").
            env: Comma-separated KEY=VALUE pairs (e.g. "API_KEY=abc,PORT=8080").
            tools: Comma-separated tool names to expose, or empty for all.
            timeout: Connection timeout in milliseconds.
        """
        import json

        parsed_args = args.split() if args else []
        parsed_env: dict[str, str] = {}
        if env:
            for pair in env.split(","):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    parsed_env[k.strip()] = v.strip()
        parsed_tools = [t.strip() for t in tools.split(",") if t.strip()] or None

        result = add_server(
            _get_registry(),
            name=name,
            command=command,
            args=parsed_args,
            env=parsed_env,
            tools=parsed_tools,
            timeout=timeout,
        )
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_remove_server(name: str) -> str:
        """Remove an MCP server from the hub.

        Args:
            name: Name of the server to remove.
        """
        import json
        result = remove_server(_get_registry(), name=name)
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_enable_server(name: str) -> str:
        """Re-enable a previously disabled MCP server.

        Args:
            name: Name of the server to enable.
        """
        import json
        result = enable_server(_get_registry(), name=name)
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_disable_server(name: str) -> str:
        """Disable an MCP server without removing it from the hub.

        The server stays registered but its tools are hidden from the agent.

        Args:
            name: Name of the server to disable.
        """
        import json
        result = disable_server(_get_registry(), name=name)
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_server_status(name: str) -> str:
        """Get detailed status for a specific MCP server.

        Args:
            name: Name of the server to inspect.
        """
        import json
        result = server_status(_get_registry(), name=name)
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_server_config(name: str) -> str:
        """Get the full configuration for an MCP server.

        Args:
            name: Name of the server to inspect.
        """
        import json
        result = get_server_config(_get_registry(), name=name)
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_discover_tools(name: str) -> str:
        """List all tools registered for a specific MCP server.

        Args:
            name: Name of the server to discover tools for.
        """
        import json
        result = discover_tools(_get_registry(), name=name)
        return json.dumps(result, indent=2)

    return server


if __name__ == "__main__":
    server = _build_server()
    server.run(transport="stdio")
