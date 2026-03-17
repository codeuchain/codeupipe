"""RED PHASE — Tests for the Hub Server Registry.

The registry tracks which sub-servers are docked in the hub
and which tools each sub-server provides.
"""

import pytest

from codeupipe.ai.hub.config import ServerConfig
from codeupipe.ai.hub.registry import ServerRegistry


@pytest.mark.unit
class TestServerRegistry:
    """Unit tests for ServerRegistry — the dock's manifest."""

    def test_register_server(self):
        """Registry can register a sub-server config."""
        registry = ServerRegistry()
        config = ServerConfig(
            name="echo",
            command="python",
            args=["-m", "codeupipe.ai.servers.echo"],
        )
        registry.register(config)
        assert registry.has("echo")

    def test_get_registered_server(self):
        """Registry returns the config for a registered server."""
        registry = ServerRegistry()
        config = ServerConfig(name="echo", command="python", args=[])
        registry.register(config)
        retrieved = registry.get("echo")
        assert retrieved is not None
        assert retrieved.name == "echo"

    def test_get_unregistered_server_returns_none(self):
        """Registry returns None for unknown server names."""
        registry = ServerRegistry()
        assert registry.get("nonexistent") is None

    def test_has_returns_false_for_unknown(self):
        """has() returns False for unregistered servers."""
        registry = ServerRegistry()
        assert registry.has("ghost") is False

    def test_list_servers(self):
        """Registry lists all registered server names."""
        registry = ServerRegistry()
        registry.register(ServerConfig(name="a", command="cmd", args=[]))
        registry.register(ServerConfig(name="b", command="cmd", args=[]))
        names = registry.list_servers()
        assert set(names) == {"a", "b"}

    def test_unregister_server(self):
        """Registry can unregister a server."""
        registry = ServerRegistry()
        registry.register(ServerConfig(name="temp", command="cmd", args=[]))
        assert registry.has("temp")
        registry.unregister("temp")
        assert not registry.has("temp")

    def test_unregister_nonexistent_is_noop(self):
        """Unregistering a non-existent server doesn't raise."""
        registry = ServerRegistry()
        registry.unregister("phantom")  # Should not raise

    def test_register_duplicate_replaces(self):
        """Re-registering the same name replaces the config."""
        registry = ServerRegistry()
        config1 = ServerConfig(name="svc", command="old", args=[])
        config2 = ServerConfig(name="svc", command="new", args=[])
        registry.register(config1)
        registry.register(config2)
        assert registry.get("svc").command == "new"

    def test_register_tool_mapping(self):
        """Registry tracks which server owns which tool."""
        registry = ServerRegistry()
        registry.register(ServerConfig(name="echo", command="cmd", args=[]))
        registry.register_tool("echo_message", "echo")
        assert registry.resolve_tool("echo_message") == "echo"

    def test_resolve_unknown_tool_returns_none(self):
        """Resolving an unknown tool returns None."""
        registry = ServerRegistry()
        assert registry.resolve_tool("no_such_tool") is None

    def test_to_mcp_configs(self):
        """Registry produces mcp_servers dict for the Copilot SDK session."""
        registry = ServerRegistry()
        registry.register(
            ServerConfig(
                name="echo",
                command="python",
                args=["-m", "codeupipe.ai.servers.echo"],
                tools=["*"],
            )
        )
        mcp_configs = registry.to_mcp_configs()
        assert "echo" in mcp_configs
        assert mcp_configs["echo"]["type"] == "local"
        assert mcp_configs["echo"]["command"] == "python"
