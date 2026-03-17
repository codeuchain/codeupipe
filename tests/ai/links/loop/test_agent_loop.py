"""RED PHASE — Tests for AgentLoopLink.

AgentLoopLink wraps a turn chain and runs it in a loop until done.
Tests verify single-turn (backward compat) and multi-turn behavior.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.agent_loop import AgentLoopLink
from codeupipe.ai.loop.state import AgentState
from codeupipe.ai.providers.base import ModelResponse


class FakeProvider:
    """Minimal mock provider for unit tests."""

    def __init__(self, responses: list[ModelResponse | None] | None = None):
        self._responses = list(responses or [ModelResponse(content="default")])
        self._idx = 0

    async def start(self, **kwargs):
        pass

    async def send(self, prompt: str) -> ModelResponse:
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp or ModelResponse()
        return ModelResponse()

    async def stop(self):
        pass


@pytest.mark.unit
class TestAgentLoopLink:
    """Unit tests for AgentLoopLink."""

    @pytest.mark.asyncio
    async def test_single_turn_completes(self):
        """Single prompt with no follow-up runs one turn and finishes."""
        link = AgentLoopLink()

        provider = FakeProvider([ModelResponse(content="Hello! How can I help?")])

        ctx = Payload({
            "provider": provider,
            "prompt": "hello",
        })

        result = await link.call(ctx)

        assert result.get("response") == "Hello! How can I help?"
        state = result.get("agent_state")
        assert state.done is True
        # With single-authority model, loop_iteration is 2: one for processing, one for detecting done
        assert state.loop_iteration == 2
        assert len(state.turn_history) == 1  # But only 1 actual turn was sent

    @pytest.mark.asyncio
    async def test_auto_creates_agent_state(self):
        """Creates AgentState automatically if not on context."""
        link = AgentLoopLink()

        provider = FakeProvider([ModelResponse(content="Done")])

        ctx = Payload({"provider": provider, "prompt": "hi"})

        result = await link.call(ctx)

        assert isinstance(result.get("agent_state"), AgentState)

    @pytest.mark.asyncio
    async def test_respects_existing_agent_state(self):
        """Uses existing AgentState with custom max_iterations."""
        link = AgentLoopLink()

        provider = FakeProvider([ModelResponse(content="Ok")])

        state = AgentState(max_iterations=3)
        ctx = Payload({
            "provider": provider,
            "prompt": "hi",
            "agent_state": state,
        })

        result = await link.call(ctx)

        assert result.get("agent_state").max_iterations == 3

    @pytest.mark.asyncio
    async def test_max_iterations_safety_cap(self):
        """Loop stops at max_iterations even with pending work."""
        link = AgentLoopLink()

        provider = FakeProvider([
            ModelResponse(content="Still working..."),
            ModelResponse(content="Still working..."),
            ModelResponse(content="Still working..."),
        ])

        # Set max_iterations=2, and always inject a follow-up
        state = AgentState(max_iterations=2)
        ctx = Payload({
            "provider": provider,
            "prompt": "start",
            "agent_state": state,
            "follow_up_prompt": "keep going",
        })

        result = await link.call(ctx)

        final_state = result.get("agent_state")
        assert final_state.done is True
        assert final_state.loop_iteration >= 2

    @pytest.mark.asyncio
    async def test_uses_custom_max_from_context(self):
        """Reads max_iterations from context when auto-creating state."""
        link = AgentLoopLink()

        provider = FakeProvider([ModelResponse(content="Done")])

        ctx = Payload({
            "provider": provider,
            "prompt": "hi",
            "max_iterations": 5,
        })

        result = await link.call(ctx)

        assert result.get("agent_state").max_iterations == 5

    @pytest.mark.asyncio
    async def test_handles_none_response(self):
        """Loop handles None content (timeout) gracefully."""
        link = AgentLoopLink()

        provider = FakeProvider([ModelResponse(content=None)])

        ctx = Payload({
            "provider": provider,
            "prompt": "hello",
        })

        result = await link.call(ctx)

        assert result.get("response") is None
        assert result.get("agent_state").done is True
