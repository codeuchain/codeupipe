"""RED PHASE — Tests for LanguageModelLink.

LanguageModelLink is the single interface between the agent and the LLM.
String in, string out. Provider is swappable via constructor or context.
"""

from unittest.mock import AsyncMock

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.language_model import LanguageModelLink
from codeupipe.ai.providers.base import ModelResponse


class FakeProvider:
    """Minimal provider for testing."""

    def __init__(self, response: ModelResponse | None = None):
        self._response = response or ModelResponse(content="fake response")
        self.send_calls: list[str] = []

    async def start(self, **kwargs):
        pass

    async def send(self, prompt: str) -> ModelResponse:
        self.send_calls.append(prompt)
        return self._response

    async def stop(self):
        pass


@pytest.mark.unit
class TestLanguageModelLink:
    """Unit tests for LanguageModelLink."""

    @pytest.mark.asyncio
    async def test_sends_prompt_and_stores_response(self):
        """Link sends next_prompt to provider and stores response."""
        provider = FakeProvider(ModelResponse(content="Hello back!"))
        link = LanguageModelLink(provider)

        ctx = Payload({"next_prompt": "Hello, agent!"})
        result = await link.call(ctx)

        assert result.get("response") == "Hello back!"
        assert provider.send_calls == ["Hello, agent!"]

    @pytest.mark.asyncio
    async def test_stores_last_response_event(self):
        """Link stores normalized event dict for downstream links."""
        tools = ({"result": {"status": "ok"}},)
        provider = FakeProvider(
            ModelResponse(content="done", tool_results=tools)
        )
        link = LanguageModelLink(provider)

        ctx = Payload({"next_prompt": "use tools"})
        result = await link.call(ctx)

        event = result.get("last_response_event")
        assert isinstance(event, dict)
        assert event["content"] == "done"
        assert len(event["tool_results"]) == 1
        assert event["tool_results"][0]["result"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_skips_when_next_prompt_is_none(self):
        """Skips sending when next_prompt is None."""
        provider = FakeProvider()
        link = LanguageModelLink(provider)

        ctx = Payload({"next_prompt": None})
        result = await link.call(ctx)

        assert result.get("response") is None
        assert result.get("last_response_event") is None
        assert provider.send_calls == []  # Not called

    @pytest.mark.asyncio
    async def test_skips_when_next_prompt_missing(self):
        """Skips sending when next_prompt is absent from context."""
        provider = FakeProvider()
        link = LanguageModelLink(provider)

        ctx = Payload({})
        result = await link.call(ctx)

        assert result.get("response") is None
        assert result.get("last_response_event") is None

    @pytest.mark.asyncio
    async def test_handles_none_content_response(self):
        """Handles provider returning None content (timeout)."""
        provider = FakeProvider(ModelResponse(content=None))
        link = LanguageModelLink(provider)

        ctx = Payload({"next_prompt": "hello?"})
        result = await link.call(ctx)

        assert result.get("response") is None
        event = result.get("last_response_event")
        assert event is not None
        assert event["content"] is None

    @pytest.mark.asyncio
    async def test_raises_without_provider(self):
        """Raises ValueError when no provider is available."""
        link = LanguageModelLink()  # No constructor injection

        ctx = Payload({"next_prompt": "hello"})
        with pytest.raises(ValueError, match="provider is required"):
            await link.call(ctx)

    @pytest.mark.asyncio
    async def test_reads_provider_from_context(self):
        """Falls back to reading provider from context."""
        provider = FakeProvider(ModelResponse(content="from context"))
        link = LanguageModelLink()  # No constructor injection

        ctx = Payload({"next_prompt": "test", "provider": provider})
        result = await link.call(ctx)

        assert result.get("response") == "from context"
        assert provider.send_calls == ["test"]

    @pytest.mark.asyncio
    async def test_constructor_provider_takes_precedence(self):
        """Constructor-injected provider takes precedence over context."""
        injected = FakeProvider(ModelResponse(content="injected"))
        context_provider = FakeProvider(ModelResponse(content="context"))

        link = LanguageModelLink(injected)

        ctx = Payload({
            "next_prompt": "test",
            "provider": context_provider,
        })
        result = await link.call(ctx)

        assert result.get("response") == "injected"
        assert injected.send_calls == ["test"]
        assert context_provider.send_calls == []  # Not used

    @pytest.mark.asyncio
    async def test_preserves_existing_context(self):
        """Link preserves other keys on context."""
        provider = FakeProvider(ModelResponse(content="ok"))
        link = LanguageModelLink(provider)

        ctx = Payload({
            "next_prompt": "test",
            "agent_state": "some_state",
            "other_key": 42,
        })
        result = await link.call(ctx)

        assert result.get("agent_state") == "some_state"
        assert result.get("other_key") == 42
        assert result.get("response") == "ok"

    @pytest.mark.asyncio
    async def test_empty_tool_results_produces_empty_list(self):
        """No tool results → empty list in event dict."""
        provider = FakeProvider(ModelResponse(content="simple"))
        link = LanguageModelLink(provider)

        ctx = Payload({"next_prompt": "test"})
        result = await link.call(ctx)

        event = result.get("last_response_event")
        assert event["tool_results"] == []
