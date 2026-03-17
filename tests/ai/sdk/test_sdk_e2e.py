"""SDK E2E tests — REAL API calls through the Agent public interface.

These tests exercise the full user workflow:
    Agent → AgentConfig → run()/ask() → AgentEvent stream

They hit the actual GitHub Copilot API. Authentication is required.

Run these tests separately:
    pytest tests/sdk/test_sdk_e2e.py -m e2e -v --tb=short

These tests will incur charges against your GitHub Copilot subscription.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from codeupipe.ai.agent import Agent, AgentConfig, AgentEvent, EventType


def _has_auth() -> bool:
    """Check if Copilot authentication is available."""
    return any([
        os.getenv("COPILOT_GITHUB_TOKEN"),
        os.getenv("GH_TOKEN"),
        os.getenv("GITHUB_TOKEN"),
    ])


@pytest.mark.e2e
class TestSDKSingleTurn:
    """Single prompt → response through the SDK public API."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_ask_returns_answer(self):
        """ask() returns a coherent string for a simple question."""
        agent = Agent()
        answer = await agent.ask("What is 9 times 7? Reply with ONLY the number.")

        assert answer is not None
        assert "63" in answer

    @pytest.mark.asyncio
    async def test_run_yields_full_event_sequence(self):
        """run() yields TURN_START → TURN_END → RESPONSE → DONE in order."""
        agent = Agent()
        events: list[AgentEvent] = []

        async for event in agent.run("Say hello in one word."):
            events.append(event)

        types = [e.type for e in events]

        assert EventType.TURN_START in types, f"Missing TURN_START. Got: {types}"
        assert EventType.TURN_END in types, f"Missing TURN_END. Got: {types}"
        assert EventType.RESPONSE in types, f"Missing RESPONSE. Got: {types}"
        assert EventType.DONE in types, f"Missing DONE. Got: {types}"

        # DONE must be the final event
        assert types[-1] == EventType.DONE

        # TURN_START must precede TURN_END
        assert types.index(EventType.TURN_START) < types.index(EventType.TURN_END)

    @pytest.mark.asyncio
    async def test_response_event_carries_content(self):
        """RESPONSE event data contains the actual LLM output."""
        agent = Agent()
        responses: list[AgentEvent] = []

        async for event in agent.run("What color is the sky? One word."):
            if event.type == EventType.RESPONSE:
                responses.append(event)

        assert len(responses) >= 1
        content = responses[0].data.get("content")
        assert content is not None
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_done_event_has_metadata(self):
        """DONE event carries final_response, total_iterations, and reason."""
        agent = Agent()
        done_event: AgentEvent | None = None

        async for event in agent.run("Say OK."):
            if event.type == EventType.DONE:
                done_event = event

        assert done_event is not None
        assert "final_response" in done_event.data
        assert "total_iterations" in done_event.data
        assert "reason" in done_event.data
        assert done_event.data["reason"] in ("complete", "max_iterations")

    @pytest.mark.asyncio
    async def test_events_are_frozen_dataclasses(self):
        """Every yielded event is a frozen AgentEvent with timestamp."""
        agent = Agent()

        async for event in agent.run("Hi."):
            assert isinstance(event, AgentEvent)
            assert event.timestamp is not None
            # Frozen — can't mutate
            with pytest.raises(AttributeError):
                event.type = EventType.ERROR  # type: ignore[misc]
            break  # One event is enough to verify


@pytest.mark.e2e
class TestSDKAskConvenience:
    """ask() convenience method — the simplest user path."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_ask_coding_question(self):
        """ask() handles a coding question end-to-end."""
        agent = Agent()
        answer = await agent.ask(
            "Write a Python one-liner that reverses a string. "
            "Reply with ONLY the code, no explanation."
        )

        assert answer is not None
        assert "[::-1]" in answer or "reversed" in answer

    @pytest.mark.asyncio
    async def test_ask_with_custom_model(self):
        """ask() respects the model config."""
        agent = Agent(config=AgentConfig(model="gpt-4.1"))
        answer = await agent.ask("What is 2 + 2? Reply ONLY the number.")

        assert answer is not None
        assert "4" in answer


@pytest.mark.e2e
class TestSDKVerboseMode:
    """verbose=True surfaces detail-level events alongside defaults."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_verbose_yields_more_events(self):
        """Verbose mode yields at least as many events as default mode."""
        prompt = "What is 3 + 4? Reply ONLY the number."

        default_agent = Agent()
        verbose_agent = Agent(config=AgentConfig(verbose=True))

        default_events = [e async for e in default_agent.run(prompt)]
        verbose_events = [e async for e in verbose_agent.run(prompt)]

        # Verbose should have >= default events
        assert len(verbose_events) >= len(default_events)

    @pytest.mark.asyncio
    async def test_default_mode_filters_verbose_events(self):
        """Default mode never yields verbose event types."""
        agent = Agent()
        events = [e async for e in agent.run("Say hello.")]

        verbose = [e for e in events if e.is_verbose]
        assert len(verbose) == 0, f"Unexpected verbose events: {[e.type for e in verbose]}"


@pytest.mark.e2e
class TestSDKEventFiltering:
    """event_types config narrows the event stream."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_filter_to_done_only(self):
        """event_types={DONE} yields only the DONE event."""
        agent = Agent(config=AgentConfig(event_types={EventType.DONE}))
        events = [e async for e in agent.run("Say hi.")]

        assert len(events) == 1
        assert events[0].type == EventType.DONE

    @pytest.mark.asyncio
    async def test_filter_to_response_and_done(self):
        """event_types={RESPONSE, DONE} yields only those two types."""
        agent = Agent(config=AgentConfig(
            event_types={EventType.RESPONSE, EventType.DONE},
        ))
        events = [e async for e in agent.run("What is 1+1? Reply ONLY the number.")]

        types = {e.type for e in events}
        assert types <= {EventType.RESPONSE, EventType.DONE}
        assert EventType.DONE in types


@pytest.mark.e2e
class TestSDKMultipleRuns:
    """Agent supports multiple sequential runs without state bleed."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_two_sequential_asks(self):
        """Two ask() calls return independent answers."""
        agent = Agent()

        answer1 = await agent.ask("What is 5 + 3? Reply ONLY the number.")
        answer2 = await agent.ask("What is 10 - 4? Reply ONLY the number.")

        assert answer1 is not None
        assert answer2 is not None
        assert "8" in answer1
        assert "6" in answer2

    @pytest.mark.asyncio
    async def test_run_then_ask(self):
        """run() followed by ask() on the same agent works cleanly."""
        agent = Agent()

        events = [e async for e in agent.run("Say OK.")]
        assert any(e.type == EventType.DONE for e in events)

        answer = await agent.ask("What is 7 + 7? Reply ONLY the number.")
        assert answer is not None
        assert "14" in answer


@pytest.mark.e2e
class TestSDKMultipleAgents:
    """Multiple Agent instances operate independently."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_concurrent_agents_no_bleed(self):
        """Two agents running concurrently produce independent results."""
        agent_a = Agent()
        agent_b = Agent(config=AgentConfig(model="gpt-4.1"))

        answer_a, answer_b = await asyncio.gather(
            agent_a.ask("What is 11 * 11? Reply ONLY the number."),
            agent_b.ask("What is 12 * 12? Reply ONLY the number."),
        )

        assert answer_a is not None
        assert answer_b is not None
        assert "121" in answer_a
        assert "144" in answer_b


@pytest.mark.e2e
class TestSDKEventSerialization:
    """Events serialize correctly for transport (JSON, SSE, websocket)."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_to_dict_round_trip(self):
        """Every event can be serialized to dict with correct keys."""
        agent = Agent()
        async for event in agent.run("Say yes."):
            d = event.to_dict()
            assert "type" in d
            assert "data" in d
            assert "timestamp" in d
            assert "iteration" in d
            assert "source" in d
            assert isinstance(d["type"], str)
            assert isinstance(d["data"], dict)
            break  # One is enough

    @pytest.mark.asyncio
    async def test_to_json_produces_valid_json(self):
        """Every event produces valid JSON."""
        import json

        agent = Agent()
        async for event in agent.run("Say no."):
            j = event.to_json()
            parsed = json.loads(j)
            assert parsed["type"] == str(event.type)
            break


@pytest.mark.e2e
class TestSDKMaxIterations:
    """max_iterations config is respected — agent stops at the safety cap."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_max_iterations_caps_loop(self):
        """With max_iterations=1, agent completes after a single turn."""
        agent = Agent(config=AgentConfig(max_iterations=1))
        events = [e async for e in agent.run("Tell me a story.")]

        done_events = [e for e in events if e.type == EventType.DONE]
        assert len(done_events) == 1

        # Should have completed (either naturally or hit cap)
        assert done_events[0].data["total_iterations"] <= 1


@pytest.mark.e2e
class TestSDKToolInteraction:
    """Agent can discover and use MCP tools via the SDK interface."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_agent_sees_tools(self):
        """Agent can report available tools from the default hub."""
        agent = Agent()
        answer = await agent.ask(
            "What tools do you have access to? List them briefly."
        )

        assert answer is not None
        # Should mention at least something about available tools
        assert len(answer) > 20

    @pytest.mark.asyncio
    async def test_tool_use_produces_response(self):
        """Agent can use echo tool and produce a response."""
        agent = Agent()
        answer = await agent.ask(
            "Use the echo tool to echo the message 'SDK test'. "
            "Then tell me what the tool returned."
        )

        assert answer is not None
        assert len(answer) > 0


@pytest.mark.e2e
class TestSDKNotificationPush:
    """push() injects notifications visible through the event stream."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_push_before_run(self):
        """Notification pushed before run() is available to the agent."""
        agent = Agent()
        agent.push("IMPORTANT: The build succeeded.", source="ci")

        # The agent should incorporate the notification
        answer = await agent.ask("What notifications do you have? Summarize them.")

        # We can't guarantee the LLM will mention it verbatim,
        # but the pipeline should not crash
        assert answer is not None
        assert len(answer) > 0


@pytest.mark.e2e
class TestSDKEdgeCases:
    """Edge cases that real users will hit."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_empty_prompt_raises(self):
        """Agent raises ValueError for an empty prompt — fail fast."""
        agent = Agent()
        with pytest.raises(ValueError, match="prompt is required"):
            await agent.ask("")

    @pytest.mark.asyncio
    async def test_long_prompt(self):
        """Agent handles a long prompt without crashing."""
        agent = Agent()
        long_prompt = "Repeat the word 'test'. " * 100 + "How many times did I say test?"
        answer = await agent.ask(long_prompt)

        assert answer is not None
        assert len(answer) > 0

    @pytest.mark.asyncio
    async def test_unicode_prompt(self):
        """Agent handles unicode characters in prompt."""
        agent = Agent()
        answer = await agent.ask("Translate 'hello' to Japanese. Reply with ONLY the Japanese text.")

        assert answer is not None
        assert len(answer) > 0

    @pytest.mark.asyncio
    async def test_event_iteration_tracking(self):
        """Events carry correct iteration numbers."""
        agent = Agent()

        async for event in agent.run("Say OK."):
            # iteration should be a non-negative integer
            assert isinstance(event.iteration, int)
            assert event.iteration >= 0
