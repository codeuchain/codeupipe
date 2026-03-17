"""Tests for the Hub Server factory functions."""

import pytest

from codeupipe.ai.hub.config import HubConfig, ServerConfig
from codeupipe.ai.hub.server import create_default_hub, create_hub_registry


@pytest.mark.unit
class TestHubServer:
    """Unit tests for hub server factory."""

    def test_create_hub_registry_from_config(self):
        """Factory creates a populated registry from HubConfig."""
        config = HubConfig(
            servers={
                "echo": ServerConfig(name="echo", command="python", args=["-m", "echo"]),
                "db": ServerConfig(name="db", command="node", args=["db-server.js"]),
            }
        )
        registry = create_hub_registry(config)
        assert registry.has("echo")
        assert registry.has("db")
        assert len(registry.list_servers()) == 2

    def test_create_hub_registry_none_config(self):
        """Factory returns empty registry for None config."""
        registry = create_hub_registry(None)
        assert len(registry.list_servers()) == 0

    def test_create_default_hub(self):
        """Default hub comes with echo server docked."""
        registry = create_default_hub()
        assert registry.has("echo")
        configs = registry.to_mcp_configs()
        assert "echo" in configs
        assert configs["echo"]["command"] == "python"
