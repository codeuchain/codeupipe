"""RED PHASE — Tests for AgentSessionChain.

Integration test: the chain orchestrates
  RegisterServers → DiscoverByIntent → InitProvider → AgentLoop → Cleanup

The AgentLoop runs a READ → WRITE → EXECUTE cycle until done.
LanguageModelLink (inside the loop) is the sole LLM interface.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from codeupipe import Payload

from codeupipe.ai.pipelines.agent_session import build_agent_session_chain
from codeupipe.ai.hub.config import ServerConfig
from codeupipe.ai.hub.registry import ServerRegistry
from codeupipe.ai.loop.state import AgentState
from codeupipe.ai.providers.base import LanguageModelProvider, ModelResponse


class FakeSessionProvider:
    """Minimal LanguageModelProvider for chain integration tests."""

    def __init__(self, content: str = "Echo: hello"):
        self._content = content

    async def start(self, **kwargs):
        pass

    async def send(self, prompt: str) -> ModelResponse:
        return ModelResponse(content=self._content)

    async def stop(self):
        pass


@pytest.mark.integration
class TestAgentSessionChain:
    """Integration tests for the agent session lifecycle chain."""

    @pytest.mark.asyncio
    async def test_chain_produces_response(self):
        """Full chain: registry → provider → loop → response → cleanup."""
        registry = ServerRegistry()
        registry.register(
            ServerConfig(name="echo", command="python", args=["-m", "echo"])
        )

        provider = FakeSessionProvider("Echo: hello")

        chain = build_agent_session_chain(provider=provider)
        ctx = Payload({
            "registry": registry,
            "model": "gpt-4.1",
            "prompt": "hello",
        })
        result = await chain.run(ctx)

        assert result.get("response") == "Echo: hello"
        assert result.get("cleaned_up") is True

        # Verify loop state was tracked
        state = result.get("agent_state")
        assert isinstance(state, AgentState)
        assert state.done is True
        # With single-authority model: one iteration to process, one to detect done
        assert state.loop_iteration == 2
        assert len(state.turn_history) == 1

    @pytest.mark.asyncio
    async def test_chain_errors_without_registry(self):
        """Chain should fail if no registry provided."""
        provider = FakeSessionProvider()
        chain = build_agent_session_chain(provider=provider)
        ctx = Payload({"model": "gpt-4.1", "prompt": "hello"})

        with pytest.raises(Exception):
            await chain.run(ctx)
