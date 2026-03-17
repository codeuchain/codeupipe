"""Tests for EventEmitterMiddleware — translates link execution into AgentEvents."""

import asyncio

import pytest
from codeupipe import Payload

from codeupipe.ai.agent.events import EventType


class TestEventEmitterMiddleware:
    """Middleware intercepts link execution and pushes AgentEvents to a queue."""

    def _make_middleware(self):
        from codeupipe.ai.agent.emitter import EventEmitterMiddleware

        queue = asyncio.Queue()
        mw = EventEmitterMiddleware(queue)
        return mw, queue

    @pytest.mark.asyncio
    async def test_before_emits_nothing_for_unknown_link(self):
        """Non-special links don't emit events on before()."""
        mw, queue = self._make_middleware()
        ctx = Payload({"agent_state": _mock_state()})

        await mw.before(_make_link("some_random"), ctx)

        assert queue.empty()

    @pytest.mark.asyncio
    async def test_after_read_input_emits_turn_start(self):
        """After read_input, emits TURN_START with the prepared prompt."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(iteration=0),
            "next_prompt": "hello world",
        })

        await mw.after(_make_link("read_input"), ctx)

        event = queue.get_nowait()
        assert event.type == EventType.TURN_START
        assert event.data["prompt"] == "hello world"
        assert event.iteration == 0

    @pytest.mark.asyncio
    async def test_after_read_input_no_prompt_skips(self):
        """After read_input with next_prompt=None, no TURN_START emitted."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(iteration=1),
            "next_prompt": None,
        })

        await mw.after(_make_link("read_input"), ctx)

        assert queue.empty()

    @pytest.mark.asyncio
    async def test_after_process_response_emits_turn_end(self):
        """After process_response, emits TURN_END with response content."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(iteration=1),
            "response": "Here you go!",
        })

        await mw.after(_make_link("process_response"), ctx)

        event = queue.get_nowait()
        assert event.type == EventType.TURN_END
        assert event.data["response"] == "Here you go!"

    @pytest.mark.asyncio
    async def test_after_process_response_emits_response_event(self):
        """After process_response, also emits a RESPONSE event with content."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(iteration=1),
            "response": "Hello!",
        })

        await mw.after(_make_link("process_response"), ctx)

        events = _drain_queue(queue)
        types = [e.type for e in events]
        assert EventType.TURN_END in types
        assert EventType.RESPONSE in types
        resp_event = [e for e in events if e.type == EventType.RESPONSE][0]
        assert resp_event.data["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_after_inject_notifications_emits_notifications(self):
        """After inject_notifications with notifications, emits NOTIFICATION events."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(iteration=2),
            "pending_notifications": [
                {"source": "ci", "message": "build passed"},
                {"source": "timer", "message": "5min elapsed"},
            ],
        })

        await mw.after(_make_link("inject_notifications"), ctx)

        events = _drain_queue(queue)
        assert len(events) == 2
        assert all(e.type == EventType.NOTIFICATION for e in events)
        assert events[0].data["message"] == "build passed"
        assert events[1].data["message"] == "5min elapsed"

    @pytest.mark.asyncio
    async def test_after_inject_notifications_empty_skips(self):
        """No notifications emitted when pending_notifications is empty."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(),
            "pending_notifications": [],
        })

        await mw.after(_make_link("inject_notifications"), ctx)

        assert queue.empty()

    @pytest.mark.asyncio
    async def test_after_check_done_emits_done(self):
        """After check_done when state.done is True, emits DONE event."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(done=True, iteration=3),
            "response": "Final answer",
        })

        await mw.after(_make_link("check_done"), ctx)

        event = queue.get_nowait()
        assert event.type == EventType.DONE
        assert event.data["final_response"] == "Final answer"
        assert event.data["total_iterations"] == 3

    @pytest.mark.asyncio
    async def test_after_check_done_not_done_skips(self):
        """After check_done when not done, no DONE event."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(done=False),
        })

        await mw.after(_make_link("check_done"), ctx)

        assert queue.empty()

    @pytest.mark.asyncio
    async def test_after_manage_state_emits_state_change(self):
        """After manage_state with state_updates, emits STATE_CHANGE."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(iteration=1),
            "state_updates": {"capabilities_added": ["tool_x"]},
        })

        await mw.after(_make_link("manage_state"), ctx)

        event = queue.get_nowait()
        assert event.type == EventType.STATE_CHANGE
        assert event.data["capabilities_added"] == ["tool_x"]

    @pytest.mark.asyncio
    async def test_after_manage_state_no_updates_skips(self):
        """After manage_state with no state_updates, skip."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(),
        })

        await mw.after(_make_link("manage_state"), ctx)

        assert queue.empty()

    @pytest.mark.asyncio
    async def test_on_error_emits_error_event(self):
        """on_error emits an ERROR event for any link failure."""
        mw, queue = self._make_middleware()
        ctx = Payload({"agent_state": _mock_state(iteration=2)})
        err = ValueError("something broke")

        # codeupipe Hook signature: on_error(filter, error, payload)
        await mw.on_error(_make_link("send_turn"), err, ctx)

        event = queue.get_nowait()
        assert event.type == EventType.ERROR
        assert event.data["error"] == "something broke"
        assert event.data["filter"] == "send_turn"
        assert event.source == "send_turn"

    @pytest.mark.asyncio
    async def test_on_error_chain_level(self):
        """on_error handles chain-level errors (link=None)."""
        mw, queue = self._make_middleware()
        ctx = Payload({"agent_state": _mock_state(iteration=3)})
        err = RuntimeError("chain-level error")

        # codeupipe Hook: on_error(None, error, payload)
        await mw.on_error(None, err, ctx)

        event = queue.get_nowait()
        assert event.type == EventType.ERROR
        assert event.data["error"] == "chain-level error"
        assert event.data["filter"] == "pipeline"

    @pytest.mark.asyncio
    async def test_iteration_from_agent_state(self):
        """Events carry the current iteration from agent_state."""
        mw, queue = self._make_middleware()
        ctx = Payload({
            "agent_state": _mock_state(iteration=5),
            "next_prompt": "prompt",
        })

        await mw.after(_make_link("read_input"), ctx)

        event = queue.get_nowait()
        assert event.iteration == 5

    @pytest.mark.asyncio
    async def test_graceful_without_agent_state(self):
        """Middleware works even if agent_state is missing (iteration=0)."""
        mw, queue = self._make_middleware()
        ctx = Payload({"next_prompt": "hello"})

        await mw.after(_make_link("read_input"), ctx)

        event = queue.get_nowait()
        assert event.iteration == 0

    @pytest.mark.asyncio
    async def test_after_none_link_skipped(self):
        """Chain-level after(None, ctx) calls are silently skipped."""
        mw, queue = self._make_middleware()
        ctx = Payload({"agent_state": _mock_state()})

        await mw.after(None, ctx)

        assert queue.empty()

    @pytest.mark.asyncio
    async def test_resolve_filter_name_convention(self):
        """Link name resolution follows CamelCase → snake_case convention."""
        from codeupipe.ai.agent.emitter import EventEmitterMiddleware

        assert EventEmitterMiddleware._resolve_filter_name(_make_link("read_input")) == "read_input"
        assert EventEmitterMiddleware._resolve_filter_name(_make_link("process_response")) == "process_response"
        assert EventEmitterMiddleware._resolve_filter_name(_make_link("check_done")) == "check_done"
        assert EventEmitterMiddleware._resolve_filter_name(_make_link("manage_state")) == "manage_state"
        assert EventEmitterMiddleware._resolve_filter_name(None) is None


# ── Helpers ───────────────────────────────────────────────────────────


def _make_link(name: str):
    """Create a mock Link whose class name follows the naming convention.

    Converts snake_case "read_input" → CamelCase "ReadInputLink" → instance.
    The emitter's _resolve_filter_name reverses this convention.
    """
    class_name = "".join(w.capitalize() for w in name.split("_")) + "Link"
    link_class = type(class_name, (), {})
    return link_class()


def _mock_state(iteration: int = 0, done: bool = False):
    """Create a minimal mock that quacks like AgentState."""
    from codeupipe.ai.loop.state import AgentState

    state = AgentState(loop_iteration=iteration)
    if done:
        state = state.mark_done()
    return state


def _drain_queue(queue: asyncio.Queue) -> list:
    """Pull all items from an asyncio.Queue (non-blocking)."""
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items
