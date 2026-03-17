"""Tests for AuditMiddleware."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from codeupipe import Payload

from codeupipe.ai.hooks.audit_event import AuditEvent
from codeupipe.ai.hooks.audit_hook import AuditMiddleware
from codeupipe.ai.hooks.audit_producer import NoopAuditSink


class CollectingSink(NoopAuditSink):
    """Audit sink that collects events for assertion."""

    def __init__(self):
        self.events: list[AuditEvent] = []

    async def send(self, event: AuditEvent) -> None:
        self.events.append(event)


class _MockFilter:
    """Lightweight stand-in for a real filter to supply a class name."""

    def __init__(self, name: str) -> None:
        # dynamically set __class__.__name__ so _filter_name() resolves it
        self._name = name

    @property
    def name(self) -> str:
        return self._name


@pytest.mark.unit
class TestAuditMiddleware:
    """Unit tests for AuditMiddleware."""

    @pytest.mark.asyncio
    async def test_captures_before_after(self):
        """before + after produces an AuditEvent."""
        sink = CollectingSink()
        mw = AuditMiddleware(sink, session_id="s1")
        payload = Payload({"prompt": "hello", "session": "mock"})
        filt = _MockFilter("test_link")

        await mw.before(filt, payload)
        await mw.after(filt, payload)

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.link_name == "test_link"
        assert event.session_id == "s1"
        assert event.duration_ms >= 0
        assert event.error is None

    @pytest.mark.asyncio
    async def test_captures_input_output_keys(self):
        """Records which keys exist on context."""
        sink = CollectingSink()
        mw = AuditMiddleware(sink)
        filt = _MockFilter("link")

        ctx_in = Payload({"a": 1, "b": 2})
        ctx_out = Payload({"a": 1, "b": 2, "c": 3})

        await mw.before(filt, ctx_in)
        await mw.after(filt, ctx_out)

        event = sink.events[0]
        assert "a" in event.input_keys
        assert "b" in event.input_keys
        assert "c" in event.output_keys

    @pytest.mark.asyncio
    async def test_on_error_captures_error(self):
        """on_error records the error string."""
        sink = CollectingSink()
        mw = AuditMiddleware(sink, session_id="err-session")
        filt = _MockFilter("bad_link")

        payload = Payload({"x": 1})
        await mw.before(filt, payload)
        await mw.on_error(filt, ValueError("kaboom"), payload)

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.link_name == "bad_link"
        assert event.error == "kaboom"
        assert event.session_id == "err-session"

    @pytest.mark.asyncio
    async def test_session_id_from_context(self):
        """If no session_id in constructor, reads from context."""
        sink = CollectingSink()
        mw = AuditMiddleware(sink)  # no session_id
        filt = _MockFilter("link")

        payload = Payload({"session_id": "from-ctx"})
        await mw.before(filt, payload)
        await mw.after(filt, payload)

        assert sink.events[0].session_id == "from-ctx"

    @pytest.mark.asyncio
    async def test_loop_iteration_from_agent_state(self):
        """Extracts loop_iteration from agent_state if present."""
        from codeupipe.ai.loop.state import AgentState

        sink = CollectingSink()
        mw = AuditMiddleware(sink)
        filt = _MockFilter("link")

        state = AgentState(loop_iteration=5)
        payload = Payload({"agent_state": state})

        await mw.before(filt, payload)
        await mw.after(filt, payload)

        assert sink.events[0].loop_iteration == 5

    @pytest.mark.asyncio
    async def test_multiple_links_tracked_independently(self):
        """Multiple before/after cycles don't interfere."""
        sink = CollectingSink()
        mw = AuditMiddleware(sink, session_id="multi")

        payload = Payload({"data": "test"})
        filt_a = _MockFilter("link_a")
        filt_b = _MockFilter("link_b")

        await mw.before(filt_a, payload)
        await mw.after(filt_a, payload)
        await mw.before(filt_b, payload)
        await mw.after(filt_b, payload)

        assert len(sink.events) == 2
        assert sink.events[0].link_name == "link_a"
        assert sink.events[1].link_name == "link_b"
