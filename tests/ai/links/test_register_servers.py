"""RED PHASE — Tests for RegisterServersLink.

RegisterServersLink takes a ServerRegistry from context and produces
the mcp_servers config dict for the session.
"""


import pytest
from codeupipe import Payload

from codeupipe.ai.hub.config import ServerConfig
from codeupipe.ai.hub.registry import ServerRegistry
from codeupipe.ai.filters.register_servers import RegisterServersLink


@pytest.mark.unit
class TestRegisterServersLink:
    """Unit tests for RegisterServersLink."""

    @pytest.mark.asyncio
    async def test_produces_mcp_servers_from_registry(self):
        """Link sets mcp_servers on context from registry."""
        link = RegisterServersLink()

        registry = ServerRegistry()
        registry.register(
            ServerConfig(name="echo", command="python", args=["-m", "echo_server"])
        )

        ctx = Payload({"registry": registry})
        result = await link.call(ctx)

        mcp_servers = result.get("mcp_servers")
        assert mcp_servers is not None
        assert "echo" in mcp_servers

    @pytest.mark.asyncio
    async def test_empty_registry_produces_empty_dict(self):
        """Link produces empty mcp_servers for empty registry."""
        link = RegisterServersLink()

        registry = ServerRegistry()
        ctx = Payload({"registry": registry})
        result = await link.call(ctx)

        assert result.get("mcp_servers") == {}

    @pytest.mark.asyncio
    async def test_raises_without_registry(self):
        """Link raises if no registry on context."""
        link = RegisterServersLink()
        ctx = Payload({})

        with pytest.raises(ValueError, match="registry"):
            await link.call(ctx)

    @pytest.mark.asyncio
    async def test_multiple_servers_all_present(self):
        """Link produces entries for all registered servers."""
        link = RegisterServersLink()

        registry = ServerRegistry()
        registry.register(ServerConfig(name="a", command="cmd_a", args=[]))
        registry.register(ServerConfig(name="b", command="cmd_b", args=[]))

        ctx = Payload({"registry": registry})
        result = await link.call(ctx)

        mcp_servers = result.get("mcp_servers")
        assert "a" in mcp_servers
        assert "b" in mcp_servers
