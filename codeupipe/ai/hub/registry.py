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
        self._disabled: set[str] = set()  # server names that are docked but paused

    # ── Server lifecycle ──────────────────────────────────────────────

    def register(self, config: ServerConfig) -> None:
        """Dock a sub-server in the hub."""
        self._servers[config.name] = config

    def unregister(self, name: str) -> None:
        """Undock a sub-server from the hub."""
        self._servers.pop(name, None)
        self._disabled.discard(name)
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

    def tools_for_server(self, server_name: str) -> list[str]:
        """List all tool names mapped to a specific server."""
        return [
            tool for tool, srv in self._tool_map.items()
            if srv == server_name
        ]

    # ── Enable / disable ──────────────────────────────────────────────

    def disable(self, name: str) -> bool:
        """Disable a docked server (excluded from mcp_configs)."""
        if name not in self._servers:
            return False
        self._disabled.add(name)
        return True

    def enable(self, name: str) -> bool:
        """Re-enable a disabled server."""
        if name not in self._servers:
            return False
        self._disabled.discard(name)
        return True

    def is_disabled(self, name: str) -> bool:
        """Check if a server is currently disabled."""
        return name in self._disabled

    # ── Copilot SDK integration ───────────────────────────────────────

    def to_mcp_configs(self) -> dict[str, dict]:
        """Produce the mcp_servers dict for Copilot SDK session config.

        This is what makes the hub transparent to the agent —
        each sub-server becomes a direct MCP server entry.
        """
        configs: dict[str, dict] = {}
        for name, cfg in self._servers.items():
            if name in self._disabled:
                continue
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
