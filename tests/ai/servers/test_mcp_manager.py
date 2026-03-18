"""RED PHASE — Tests for the MCP Manager server.

The MCP Manager is an MCP server whose tools let the agent manage
the hub's server registry on behalf of the user: list, add, remove,
enable, disable, inspect, and discover tools on docked servers.

Tests target the pure-function layer (no FastMCP dependency).
"""

import pytest

from codeupipe.ai.hub.config import ServerConfig
from codeupipe.ai.hub.registry import ServerRegistry
from codeupipe.ai.servers.mcp_manager import (
    add_server,
    disable_server,
    discover_tools,
    enable_server,
    get_server_config,
    list_servers,
    remove_server,
    server_status,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def registry() -> ServerRegistry:
    """Fresh registry with one echo server docked."""
    reg = ServerRegistry()
    reg.register(
        ServerConfig(
            name="echo",
            command="python",
            args=["-m", "codeupipe.ai.servers.echo"],
            tools=["*"],
        )
    )
    reg.register_tool("echo_message", "echo")
    reg.register_tool("echo_reverse", "echo")
    return reg


# ── list_servers ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestListServers:
    """Tests for list_servers tool function."""

    def test_returns_list_of_names(self, registry: ServerRegistry):
        result = list_servers(registry)
        assert isinstance(result, dict)
        assert "servers" in result
        assert "echo" in result["servers"]

    def test_empty_registry(self):
        result = list_servers(ServerRegistry())
        assert result["servers"] == []

    def test_multiple_servers(self, registry: ServerRegistry):
        registry.register(
            ServerConfig(name="db", command="node", args=["db.js"])
        )
        result = list_servers(registry)
        assert set(result["servers"]) == {"echo", "db"}

    def test_count_field(self, registry: ServerRegistry):
        result = list_servers(registry)
        assert result["count"] == 1


# ── add_server ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAddServer:
    """Tests for add_server tool function."""

    def test_adds_new_server(self, registry: ServerRegistry):
        result = add_server(
            registry,
            name="weather",
            command="python",
            args=["-m", "weather_server"],
        )
        assert result["added"] is True
        assert registry.has("weather")

    def test_returns_config_summary(self, registry: ServerRegistry):
        result = add_server(
            registry,
            name="db",
            command="node",
            args=["db.js"],
            env={"DB_URL": "sqlite://"},
        )
        assert result["name"] == "db"
        assert result["command"] == "node"

    def test_replaces_existing_server(self, registry: ServerRegistry):
        result = add_server(
            registry,
            name="echo",
            command="node",
            args=["new-echo.js"],
        )
        assert result["added"] is True
        assert result["replaced"] is True
        assert registry.get("echo").command == "node"

    def test_new_server_not_replaced(self, registry: ServerRegistry):
        result = add_server(
            registry,
            name="brand-new",
            command="python",
            args=[],
        )
        assert result["replaced"] is False

    def test_default_tools_wildcard(self, registry: ServerRegistry):
        add_server(registry, name="x", command="cmd", args=[])
        config = registry.get("x")
        assert config.tools == ["*"]

    def test_custom_tools_list(self, registry: ServerRegistry):
        add_server(
            registry,
            name="x",
            command="cmd",
            args=[],
            tools=["tool_a", "tool_b"],
        )
        config = registry.get("x")
        assert config.tools == ["tool_a", "tool_b"]

    def test_env_passed_through(self, registry: ServerRegistry):
        add_server(
            registry,
            name="x",
            command="cmd",
            args=[],
            env={"API_KEY": "secret"},
        )
        config = registry.get("x")
        assert config.env == {"API_KEY": "secret"}


# ── remove_server ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestRemoveServer:
    """Tests for remove_server tool function."""

    def test_removes_existing_server(self, registry: ServerRegistry):
        result = remove_server(registry, name="echo")
        assert result["removed"] is True
        assert not registry.has("echo")

    def test_removes_tool_mappings(self, registry: ServerRegistry):
        remove_server(registry, name="echo")
        assert registry.resolve_tool("echo_message") is None
        assert registry.resolve_tool("echo_reverse") is None

    def test_nonexistent_server_returns_false(self, registry: ServerRegistry):
        result = remove_server(registry, name="ghost")
        assert result["removed"] is False


# ── enable_server / disable_server ────────────────────────────────────


@pytest.mark.unit
class TestEnableDisableServer:
    """Tests for enable/disable tool functions."""

    def test_disable_removes_from_configs(self, registry: ServerRegistry):
        result = disable_server(registry, name="echo")
        assert result["disabled"] is True
        # Server is still registered but marked disabled
        assert result["name"] == "echo"

    def test_disable_nonexistent(self, registry: ServerRegistry):
        result = disable_server(registry, name="ghost")
        assert result["disabled"] is False

    def test_enable_server(self, registry: ServerRegistry):
        disable_server(registry, name="echo")
        result = enable_server(registry, name="echo")
        assert result["enabled"] is True

    def test_enable_nonexistent(self, registry: ServerRegistry):
        result = enable_server(registry, name="ghost")
        assert result["enabled"] is False


# ── server_status ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestServerStatus:
    """Tests for server_status tool function."""

    def test_returns_config_for_existing(self, registry: ServerRegistry):
        result = server_status(registry, name="echo")
        assert result["found"] is True
        assert result["name"] == "echo"
        assert result["command"] == "python"
        assert "tools" in result

    def test_returns_not_found(self, registry: ServerRegistry):
        result = server_status(registry, name="missing")
        assert result["found"] is False

    def test_includes_tool_mappings(self, registry: ServerRegistry):
        result = server_status(registry, name="echo")
        assert "echo_message" in result["tools"]
        assert "echo_reverse" in result["tools"]


# ── get_server_config ─────────────────────────────────────────────────


@pytest.mark.unit
class TestGetServerConfig:
    """Tests for get_server_config tool function."""

    def test_returns_full_config(self, registry: ServerRegistry):
        result = get_server_config(registry, name="echo")
        assert result["found"] is True
        assert result["config"]["name"] == "echo"
        assert result["config"]["command"] == "python"
        assert result["config"]["args"] == ["-m", "codeupipe.ai.servers.echo"]

    def test_not_found(self, registry: ServerRegistry):
        result = get_server_config(registry, name="nope")
        assert result["found"] is False


# ── discover_tools ────────────────────────────────────────────────────


@pytest.mark.unit
class TestDiscoverTools:
    """Tests for discover_tools tool function."""

    def test_returns_tools_for_server(self, registry: ServerRegistry):
        result = discover_tools(registry, name="echo")
        assert result["found"] is True
        assert "echo_message" in result["tools"]

    def test_not_found(self, registry: ServerRegistry):
        result = discover_tools(registry, name="nope")
        assert result["found"] is False
        assert result["tools"] == []

    def test_server_with_no_tools(self, registry: ServerRegistry):
        registry.register(
            ServerConfig(name="empty", command="cmd", args=[])
        )
        result = discover_tools(registry, name="empty")
        assert result["found"] is True
        assert result["tools"] == []
