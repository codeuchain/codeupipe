"""Tests for AgentEvent and EventType — the SDK's event protocol."""

import pytest
from datetime import datetime, timezone


class TestEventType:
    """EventType enum covers all public event kinds."""

    def test_has_turn_start(self):
        from codeupipe.ai.agent.events import EventType
        assert EventType.TURN_START == "turn_start"

    def test_has_turn_end(self):
        from codeupipe.ai.agent.events import EventType
        assert EventType.TURN_END == "turn_end"

    def test_has_response(self):
        from codeupipe.ai.agent.events import EventType
        assert EventType.RESPONSE == "response"

    def test_has_tool_call(self):
        from codeupipe.ai.agent.events import EventType
        assert EventType.TOOL_CALL == "tool_call"

    def test_has_tool_result(self):
        from codeupipe.ai.agent.events import EventType
        assert EventType.TOOL_RESULT == "tool_result"

    def test_has_notification(self):
        from codeupipe.ai.agent.events import EventType
        assert EventType.NOTIFICATION == "notification"

    def test_has_state_change(self):
        from codeupipe.ai.agent.events import EventType
        assert EventType.STATE_CHANGE == "state_change"

    def test_has_error(self):
        from codeupipe.ai.agent.events import EventType
        assert EventType.ERROR == "error"

    def test_has_done(self):
        from codeupipe.ai.agent.events import EventType
        assert EventType.DONE == "done"

    def test_all_types_count(self):
        """There should be exactly 10 public event types."""
        from codeupipe.ai.agent.events import EventType
        assert len(EventType) == 10


class TestAgentEvent:
    """AgentEvent is frozen, serializable, and carries typed payloads."""

    def test_create_minimal_event(self):
        """Events can be created with just type and data."""
        from codeupipe.ai.agent.events import AgentEvent, EventType

        event = AgentEvent(
            type=EventType.TURN_START,
            data={"prompt": "hello"},
        )
        assert event.type == EventType.TURN_START
        assert event.data == {"prompt": "hello"}

    def test_event_has_timestamp(self):
        """Events auto-generate a UTC timestamp."""
        from codeupipe.ai.agent.events import AgentEvent, EventType

        event = AgentEvent(type=EventType.DONE, data={})
        assert isinstance(event.timestamp, datetime)
        assert event.timestamp.tzinfo == timezone.utc

    def test_event_defaults(self):
        """Iteration defaults to 0, source defaults to 'agent'."""
        from codeupipe.ai.agent.events import AgentEvent, EventType

        event = AgentEvent(type=EventType.RESPONSE, data={"content": "hi"})
        assert event.iteration == 0
        assert event.source == "agent"

    def test_event_custom_fields(self):
        """All fields can be set explicitly."""
        from codeupipe.ai.agent.events import AgentEvent, EventType

        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        event = AgentEvent(
            type=EventType.TOOL_CALL,
            data={"tool_name": "echo", "arguments": {"msg": "hi"}},
            timestamp=ts,
            iteration=3,
            source="tool_continuation",
        )
        assert event.iteration == 3
        assert event.source == "tool_continuation"
        assert event.timestamp == ts

    def test_event_is_frozen(self):
        """Events are immutable after creation."""
        from dataclasses import FrozenInstanceError

        from codeupipe.ai.agent.events import AgentEvent, EventType

        event = AgentEvent(type=EventType.DONE, data={})
        with pytest.raises((AttributeError, FrozenInstanceError)):
            event.type = EventType.ERROR  # type: ignore[misc]

    def test_event_to_dict(self):
        """Events serialize to plain dict for JSON/SSE transport."""
        from codeupipe.ai.agent.events import AgentEvent, EventType

        event = AgentEvent(
            type=EventType.RESPONSE,
            data={"content": "hello"},
            iteration=1,
            source="agent",
        )
        d = event.to_dict()
        assert d["type"] == "response"
        assert d["data"] == {"content": "hello"}
        assert d["iteration"] == 1
        assert d["source"] == "agent"
        assert "timestamp" in d

    def test_event_to_json(self):
        """Events serialize to JSON string."""
        import json
        from codeupipe.ai.agent.events import AgentEvent, EventType

        event = AgentEvent(
            type=EventType.TURN_END,
            data={"response": "done", "tool_calls_count": 2},
        )
        raw = event.to_json()
        parsed = json.loads(raw)
        assert parsed["type"] == "turn_end"
        assert parsed["data"]["tool_calls_count"] == 2

    def test_event_is_verbose_default(self):
        """Non-verbose event types: TURN_START, TURN_END, RESPONSE, DONE, ERROR."""
        from codeupipe.ai.agent.events import AgentEvent, EventType

        # These should be default (non-verbose)
        for evt_type in (EventType.TURN_START, EventType.TURN_END,
                         EventType.RESPONSE, EventType.DONE, EventType.ERROR):
            event = AgentEvent(type=evt_type, data={})
            assert event.is_verbose is False, f"{evt_type} should be non-verbose"

    def test_event_is_verbose_detail(self):
        """Verbose event types: TOOL_CALL, TOOL_RESULT, NOTIFICATION, STATE_CHANGE."""
        from codeupipe.ai.agent.events import AgentEvent, EventType

        for evt_type in (EventType.TOOL_CALL, EventType.TOOL_RESULT,
                         EventType.NOTIFICATION, EventType.STATE_CHANGE):
            event = AgentEvent(type=evt_type, data={})
            assert event.is_verbose is True, f"{evt_type} should be verbose"
