"""Integration tests — Agent SDK wired to real chains with mocked provider.

These tests verify that the EventEmitterMiddleware correctly captures
events from the actual chain execution (real links, mocked LLM via
the LanguageModelProvider abstraction).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codeupipe.ai.providers.base import ModelResponse
from codeupipe.ai.agent import Agent, AgentConfig, AgentEvent, EventType


class FakeIntegrationProvider:
    """LanguageModelProvider stub for SDK integration tests."""

    def __init__(self, content: str = "default"):
        self._content = content

    async def start(self, **kwargs):
        pass

    async def send(self, prompt: str) -> ModelResponse:
        return ModelResponse(content=self._content)

    async def stop(self):
        pass


class TestAgentIntegration:
    """Agent.run() produces correct events from real chain execution."""

    @pytest.mark.asyncio
    async def test_single_turn_event_sequence(self):
        """Single-turn run produces TURN_START → TURN_END → RESPONSE → DONE."""
        agent = Agent()

        with _patch_provider("I'm the echo agent!"):
            events = [e async for e in agent.run("hello")]

        types = [e.type for e in events]
        assert EventType.TURN_START in types
        assert EventType.TURN_END in types
        assert EventType.RESPONSE in types
        assert EventType.DONE in types

        # DONE should be last
        assert types[-1] == EventType.DONE

    @pytest.mark.asyncio
    async def test_response_content_flows_through(self):
        """The RESPONSE event carries the actual LLM response content."""
        agent = Agent()

        with _patch_provider("Hello from the agent!"):
            events = [e async for e in agent.run("hi")]

        responses = [e for e in events if e.type == EventType.RESPONSE]
        assert len(responses) >= 1
        assert responses[0].data["content"] == "Hello from the agent!"

    @pytest.mark.asyncio
    async def test_ask_integration(self):
        """ask() returns the response string through real chains."""
        agent = Agent()

        with _patch_provider("42"):
            answer = await agent.ask("What is 6 * 7?")

        assert answer == "42"

    @pytest.mark.asyncio
    async def test_done_event_has_final_response(self):
        """DONE event carries the final response."""
        agent = Agent()

        with _patch_provider("All done!"):
            events = [e async for e in agent.run("finish")]

        done = [e for e in events if e.type == EventType.DONE][0]
        assert done.data["final_response"] == "All done!"
        assert done.data["reason"] == "complete"

    @pytest.mark.asyncio
    async def test_verbose_mode_includes_all_events(self):
        """With verbose=True, even internal events come through."""
        agent = Agent(config=AgentConfig(verbose=True))

        with _patch_provider("Verbose output"):
            events = [e async for e in agent.run("hello")]

        # Should have more events in verbose mode
        assert len(events) >= 3  # At minimum: TURN_START, TURN_END, RESPONSE, DONE

    @pytest.mark.asyncio
    async def test_event_types_filter_integration(self):
        """event_types filter only passes matching events."""
        agent = Agent(config=AgentConfig(event_types={EventType.DONE}))

        with _patch_provider("filtered"):
            events = [e async for e in agent.run("hello")]

        assert all(e.type == EventType.DONE for e in events)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_multiple_runs_independent(self):
        """Each run() is independent — fresh session, no state bleed."""
        agent = Agent()

        with _patch_provider("First"):
            answer1 = await agent.ask("first")

        with _patch_provider("Second"):
            answer2 = await agent.ask("second")

        assert answer1 == "First"
        assert answer2 == "Second"

    @pytest.mark.asyncio
    async def test_push_notification_available_in_queue(self):
        """push() adds notification that persists across runs."""
        agent = Agent()
        agent.push("Build passed!", source="ci")

        assert not agent._notification_queue.is_empty()

    @pytest.mark.asyncio
    async def test_public_imports(self):
        """All public API symbols are importable from top-level."""
        from codeupipe.ai.agent import (
            Agent,
            AgentConfig,
            AgentEvent,
            EventType,
            ServerDef,
        )

        assert Agent is not None
        assert AgentConfig is not None
        assert AgentEvent is not None
        assert EventType is not None
        assert ServerDef is not None


# ── Helpers ──────────────────────────────────────────────────────────


def _patch_provider(content: str):
    """Patch CopilotClient so CopilotProvider uses a mocked LLM.

    CopilotProvider does a lazy ``from copilot import CopilotClient``
    inside its start() method. We patch that import target to return
    a mock client whose session returns our desired content.
    """
    mock_event = MagicMock()
    mock_event.data.content = content
    mock_event.data.tool_results = None

    mock_session = MagicMock()
    mock_session.send_and_wait = AsyncMock(return_value=mock_event)
    mock_session.destroy = AsyncMock()

    mock_client = MagicMock()
    mock_client.start = AsyncMock()
    mock_client.create_session = AsyncMock(return_value=mock_session)
    mock_client.stop = AsyncMock()

    return patch("copilot.CopilotClient", return_value=mock_client)
