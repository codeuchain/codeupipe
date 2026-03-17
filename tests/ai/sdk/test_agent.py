"""Tests for Agent — the primary SDK entry point."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codeupipe.ai.agent.config import AgentConfig
from codeupipe.ai.agent.events import EventType


class TestAgentInit:
    """Agent initializes with config and defaults."""

    def test_create_with_no_config(self):
        """Agent can be created with zero configuration."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        assert agent.config.model == "gpt-4.1"
        assert agent.config.max_iterations == 10

    def test_create_with_config(self):
        """Agent accepts an AgentConfig for customization."""
        from codeupipe.ai.agent.agent import Agent

        cfg = AgentConfig(model="claude-sonnet-4", max_iterations=5)
        agent = Agent(config=cfg)
        assert agent.config.model == "claude-sonnet-4"
        assert agent.config.max_iterations == 5

    def test_multiple_instances(self):
        """Multiple agents can be created with different configs."""
        from codeupipe.ai.agent.agent import Agent

        a1 = Agent(config=AgentConfig(model="gpt-4.1"))
        a2 = Agent(config=AgentConfig(model="claude-sonnet-4"))
        assert a1.config.model != a2.config.model


class TestAgentRun:
    """Agent.run() returns an async generator of AgentEvents."""

    @pytest.mark.asyncio
    async def test_run_yields_events(self):
        """run() yields AgentEvent objects."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        events = []

        with _mock_chain_execution():
            async for event in agent.run("hello"):
                events.append(event)

        assert len(events) > 0
        # All yielded objects are AgentEvents
        from codeupipe.ai.agent.events import AgentEvent
        assert all(isinstance(e, AgentEvent) for e in events)

    @pytest.mark.asyncio
    async def test_run_yields_done_event(self):
        """run() always ends with a DONE event."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()

        with _mock_chain_execution():
            events = [e async for e in agent.run("hello")]

        last = events[-1]
        assert last.type == EventType.DONE

    @pytest.mark.asyncio
    async def test_run_yields_turn_start(self):
        """run() yields a TURN_START event."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()

        with _mock_chain_execution():
            events = [e async for e in agent.run("hello")]

        types = [e.type for e in events]
        assert EventType.TURN_START in types

    @pytest.mark.asyncio
    async def test_run_yields_response(self):
        """run() yields a RESPONSE event with the agent's content."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()

        with _mock_chain_execution(response="Hello! I can help."):
            events = [e async for e in agent.run("hello")]

        responses = [e for e in events if e.type == EventType.RESPONSE]
        assert len(responses) >= 1
        assert responses[0].data["content"] == "Hello! I can help."

    @pytest.mark.asyncio
    async def test_run_verbose_includes_detail_events(self):
        """With verbose=True, run() includes tool/state events."""
        from codeupipe.ai.agent.agent import Agent

        cfg = AgentConfig(verbose=True)
        agent = Agent(config=cfg)

        with _mock_chain_execution(response="done"):
            events = [e async for e in agent.run("hello")]

        # All events are yielded including verbose ones
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_run_default_filters_verbose_events(self):
        """With verbose=False (default), verbose events are filtered out."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()  # verbose=False by default

        with _mock_chain_execution(response="done"):
            events = [e async for e in agent.run("hello")]

        # No verbose events in default mode
        verbose_events = [e for e in events if e.is_verbose]
        assert len(verbose_events) == 0

    @pytest.mark.asyncio
    async def test_run_event_types_filter(self):
        """event_types config filters to specific event types only."""
        from codeupipe.ai.agent.agent import Agent

        cfg = AgentConfig(event_types={EventType.DONE})
        agent = Agent(config=cfg)

        with _mock_chain_execution(response="done"):
            events = [e async for e in agent.run("hello")]

        assert all(e.type == EventType.DONE for e in events)

    @pytest.mark.asyncio
    async def test_run_multiple_calls(self):
        """Agent can run() multiple times (each fresh session)."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()

        with _mock_chain_execution(response="first"):
            events1 = [e async for e in agent.run("prompt 1")]

        with _mock_chain_execution(response="second"):
            events2 = [e async for e in agent.run("prompt 2")]

        r1 = [e for e in events1 if e.type == EventType.RESPONSE]
        r2 = [e for e in events2 if e.type == EventType.RESPONSE]
        assert r1[0].data["content"] == "first"
        assert r2[0].data["content"] == "second"


class TestAgentAsk:
    """Agent.ask() is the convenience method that returns just a string."""

    @pytest.mark.asyncio
    async def test_ask_returns_string(self):
        """ask() returns the agent's final response as a string."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()

        with _mock_chain_execution(response="The answer is 42"):
            answer = await agent.ask("What is the meaning?")

        assert answer == "The answer is 42"

    @pytest.mark.asyncio
    async def test_ask_returns_none_on_no_response(self):
        """ask() returns None if agent produced no response."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()

        with _mock_chain_execution(response=None):
            answer = await agent.ask("hello")

        assert answer is None


class TestAgentPush:
    """Agent.push() injects messages into the notification queue."""

    @pytest.mark.asyncio
    async def test_push_queues_notification(self):
        """push() adds a notification to the agent's queue."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()

        agent.push("Build passed!", source="ci")

        # Verify notification is in the queue
        assert not agent._notification_queue.is_empty()
        notifications = agent._notification_queue.drain()
        assert len(notifications) == 1
        assert notifications[0].message == "Build passed!"
        assert notifications[0].source_name == "ci"

    @pytest.mark.asyncio
    async def test_push_multiple(self):
        """Multiple push() calls queue in order."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()

        agent.push("first")
        agent.push("second")

        assert agent._notification_queue.size == 2

    @pytest.mark.asyncio
    async def test_push_default_source(self):
        """Default source is 'user'."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.push("hello")

        notifications = agent._notification_queue.drain()
        assert notifications[0].source_name == "user"


class TestAgentCancel:
    """Agent.cancel() signals the loop to stop."""

    @pytest.mark.asyncio
    async def test_cancel_sets_flag(self):
        """cancel() sets the cancellation flag."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        assert agent._cancelled is False
        agent.cancel()
        assert agent._cancelled is True


# ── Mock helpers ─────────────────────────────────────────────────────


def _mock_chain_execution(response: str | None = "OK"):
    """Context manager that patches the chain to emit standard events.

    The mock chain simulates a single-turn execution:
    1. TURN_START (from read_input)
    2. TURN_END + RESPONSE (from process_response)
    3. DONE (from check_done)
    """
    from codeupipe.ai.agent.emitter import EventEmitterMiddleware
    from codeupipe.ai.agent.events import AgentEvent

    async def fake_run(ctx):
        """Simulate chain execution by firing middleware events."""
        # Find the EventEmitterMiddleware on the chain
        # We'll directly push events to verify the Agent's event stream
        return ctx

    # We'll patch the internal _execute method that Agent calls
    return patch(
        "codeupipe.ai.agent.agent.Agent._execute",
        new_callable=lambda: _make_mock_execute(response),
    )


def _make_mock_execute(response: str | None):
    """Create a mock _execute that pushes events into the queue."""
    from codeupipe.ai.agent.events import AgentEvent

    class MockExecute:
        def __call__(self, *args, **kwargs):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    # Return an async function that pushes events to the queue
    async def mock_execute(self_agent, prompt, queue):
        """Push realistic events to simulate a single-turn run."""
        await queue.put(AgentEvent(
            type=EventType.TURN_START,
            data={"prompt": prompt, "iteration": 0},
            iteration=0,
            source="read_input",
        ))

        if response is not None:
            await queue.put(AgentEvent(
                type=EventType.TURN_END,
                data={"response": response, "iteration": 0},
                iteration=0,
                source="process_response",
            ))
            await queue.put(AgentEvent(
                type=EventType.RESPONSE,
                data={"content": response},
                iteration=0,
                source="process_response",
            ))

        await queue.put(AgentEvent(
            type=EventType.DONE,
            data={
                "final_response": response,
                "total_iterations": 1,
                "reason": "complete",
            },
            iteration=1,
            source="check_done",
        ))

    return mock_execute
