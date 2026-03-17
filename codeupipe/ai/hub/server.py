"""MCP Hub Server — the dock.

This module provides the factory for creating a hub configuration
that aggregates all sub-servers into a single MCP entry point
for the Copilot SDK agent.

The agent never knows about this layer — it just sees tools.
"""

from codeupipe.ai.hub.config import HubConfig, ServerConfig
from codeupipe.ai.hub.registry import ServerRegistry


def create_hub_registry(config: HubConfig | None = None) -> ServerRegistry:
    """Create and populate a ServerRegistry from a HubConfig.

    Args:
        config: Hub configuration with sub-server definitions.
                If None, returns an empty registry.

    Returns:
        A populated ServerRegistry ready to produce mcp_servers configs.
    """
    registry = ServerRegistry()

    if config:
        for name, server_config in config.servers.items():
            registry.register(server_config)

    return registry


def create_default_hub() -> ServerRegistry:
    """Create the default hub with the echo server docked.

    This is the out-of-the-box experience — one echo server
    demonstrating the dock pattern.
    """
    config = HubConfig(
        servers={
            "echo": ServerConfig(
                name="echo",
                command="python",
                args=["-m", "codeupipe.ai.servers.echo"],
                tools=["*"],
            ),
        }
    )
    return create_hub_registry(config)
