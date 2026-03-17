"""RED PHASE — Tests for InitProviderLink.

InitProviderLink replaces InitClientLink + CreateSessionLink.
It calls provider.start() with mcp_servers from context and places
the provider on context for LanguageModelLink.
"""

from unittest.mock import AsyncMock

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.init_provider import InitProviderLink
from codeupipe.ai.providers.base import ModelResponse


class FakeProvider:
    """Minimal provider for testing."""

    def __init__(self):
        self.started = False
        self.start_kwargs: dict = {}

    async def start(self, **kwargs):
        self.started = True
        self.start_kwargs = kwargs

    async def send(self, prompt: str) -> ModelResponse:
        return ModelResponse(content="fake")

    async def stop(self):
        pass


@pytest.mark.unit
class TestInitProviderLink:
    """Unit tests for InitProviderLink."""

    @pytest.mark.asyncio
    async def test_starts_provider(self):
        """Calls provider.start() during execution."""
        provider = FakeProvider()
        link = InitProviderLink(provider)

        ctx = Payload({})
        await link.call(ctx)

        assert provider.started is True

    @pytest.mark.asyncio
    async def test_passes_mcp_servers(self):
        """Passes mcp_servers from context to provider.start()."""
        provider = FakeProvider()
        link = InitProviderLink(provider)

        servers = {"server1": {"command": "node", "args": ["server.js"]}}
        ctx = Payload({"mcp_servers": servers})
        await link.call(ctx)

        assert provider.start_kwargs["mcp_servers"] == servers

    @pytest.mark.asyncio
    async def test_default_empty_mcp_servers(self):
        """Uses empty dict when mcp_servers not on context."""
        provider = FakeProvider()
        link = InitProviderLink(provider)

        ctx = Payload({})
        await link.call(ctx)

        assert provider.start_kwargs["mcp_servers"] == {}

    @pytest.mark.asyncio
    async def test_places_provider_on_context(self):
        """Provider is placed on context for LanguageModelLink."""
        provider = FakeProvider()
        link = InitProviderLink(provider)

        ctx = Payload({})
        result = await link.call(ctx)

        assert result.get("provider") is provider

    @pytest.mark.asyncio
    async def test_preserves_existing_context(self):
        """Other context keys survive through the link."""
        provider = FakeProvider()
        link = InitProviderLink(provider)

        ctx = Payload({
            "model": "gpt-4.1",
            "prompt": "hello",
            "mcp_servers": {"s1": {}},
        })
        result = await link.call(ctx)

        assert result.get("model") == "gpt-4.1"
        assert result.get("prompt") == "hello"
        assert result.get("provider") is provider
