"""Server Registry — the dock's manifest of sub-servers.

Tracks which sub-servers are docked, which tools each provides,
and produces the mcp_servers config dict for the Copilot SDK session.
"""

from codeupipe.ai.hub.config import ServerConfig


class ServerRegistry:
    """Registry of docked MCP sub-servers.

    Responsibilities:
        - Register / unregister sub-server configs
        - Map tool names to owning server
        - Produce mcp_servers dict for Copilot SDK session config
    """

    def __init__(self) -> None:
        self._servers: dict[str, ServerConfig] = {}
        self._tool_map: dict[str, str] = {}  # tool_name -> server_name

    # ── Server lifecycle ──────────────────────────────────────────────

    def register(self, config: ServerConfig) -> None:
        """Dock a sub-server in the hub."""
        self._servers[config.name] = config

    def unregister(self, name: str) -> None:
        """Undock a sub-server from the hub."""
        self._servers.pop(name, None)
        # Clean up tool mappings for this server
        self._tool_map = {
            tool: srv for tool, srv in self._tool_map.items() if srv != name
        }

    def has(self, name: str) -> bool:
        """Check if a server is docked."""
        return name in self._servers

    def get(self, name: str) -> ServerConfig | None:
        """Get config for a docked server."""
        return self._servers.get(name)

    def list_servers(self) -> list[str]:
        """List all docked server names."""
        return list(self._servers.keys())

    # ── Tool mapping ──────────────────────────────────────────────────

    def register_tool(self, tool_name: str, server_name: str) -> None:
        """Map a tool name to the server that provides it."""
        self._tool_map[tool_name] = server_name

    def resolve_tool(self, tool_name: str) -> str | None:
        """Resolve which server owns a given tool."""
        return self._tool_map.get(tool_name)

    # ── Copilot SDK integration ───────────────────────────────────────

    def to_mcp_configs(self) -> dict[str, dict]:
        """Produce the mcp_servers dict for Copilot SDK session config.

        This is what makes the hub transparent to the agent —
        each sub-server becomes a direct MCP server entry.
        """
        configs: dict[str, dict] = {}
        for name, cfg in self._servers.items():
            entry: dict = {
                "type": "local",
                "command": cfg.command,
                "args": cfg.args,
                "tools": cfg.tools,
                "timeout": cfg.timeout,
            }
            if cfg.env:
                entry["env"] = cfg.env
            if cfg.cwd:
                entry["cwd"] = cfg.cwd
            configs[name] = entry
        return configs
