"""Tests for AuditEvent dataclass."""

import pytest
from datetime import datetime, timezone

from codeupipe.ai.hooks.audit_event import AuditEvent, ContextAttribution


@pytest.mark.unit
class TestAuditEvent:
    """Unit tests for AuditEvent."""

    def test_frozen(self):
        """AuditEvent is immutable."""
        event = AuditEvent(
            timestamp=AuditEvent.now(),
            session_id="s1",
            loop_iteration=1,
            link_name="test_link",
            input_keys=("a",),
            output_keys=("a", "b"),
            duration_ms=42.5,
        )
        with pytest.raises(AttributeError):
            event.link_name = "changed"  # type: ignore[misc]

    def test_defaults(self):
        """Error and metadata default to None."""
        event = AuditEvent(
            timestamp=AuditEvent.now(),
            session_id="s1",
            loop_iteration=0,
            link_name="link",
            input_keys=(),
            output_keys=(),
            duration_ms=0.0,
        )
        assert event.error is None
        assert event.metadata is None

    def test_to_dict(self):
        """Serialization to plain dict."""
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        event = AuditEvent(
            timestamp=ts,
            session_id="session-42",
            loop_iteration=3,
            link_name="process_response",
            input_keys=("prompt", "session"),
            output_keys=("prompt", "session", "response"),
            duration_ms=150.3,
            error=None,
            metadata={"tool_count": 2},
        )
        d = event.to_dict()

        assert d["timestamp"] == "2025-01-01T00:00:00+00:00"
        assert d["session_id"] == "session-42"
        assert d["loop_iteration"] == 3
        assert d["link_name"] == "process_response"
        assert d["input_keys"] == ["prompt", "session"]
        assert d["output_keys"] == ["prompt", "session", "response"]
        assert d["duration_ms"] == 150.3
        assert d["error"] is None
        assert d["metadata"] == {"tool_count": 2}

    def test_to_dict_with_error(self):
        """Serialization includes error string."""
        event = AuditEvent(
            timestamp=AuditEvent.now(),
            session_id="s1",
            loop_iteration=1,
            link_name="bad_link",
            input_keys=("x",),
            output_keys=(),
            duration_ms=5.0,
            error="Timeout exceeded",
        )
        d = event.to_dict()
        assert d["error"] == "Timeout exceeded"

    def test_now_utc(self):
        """now() returns UTC timestamp."""
        ts = AuditEvent.now()
        assert ts.tzinfo == timezone.utc


@pytest.mark.unit
class TestContextAttribution:
    """Unit tests for ContextAttribution."""

    def test_frozen(self):
        """ContextAttribution is immutable."""
        attr = ContextAttribution(
            source="turns",
            estimated_tokens=500,
        )
        with pytest.raises(AttributeError):
            attr.source = "tools"  # type: ignore[misc]

    def test_defaults(self):
        """Default percentage, item_count, metadata."""
        attr = ContextAttribution(
            source="tools",
            estimated_tokens=100,
        )
        assert attr.percentage == 0.0
        assert attr.item_count == 0
        assert attr.metadata == {}

    def test_to_dict(self):
        """Serialization to plain dict."""
        attr = ContextAttribution(
            source="capabilities",
            estimated_tokens=2000,
            percentage=45.2,
            item_count=12,
            metadata={"types": ["TOOL", "SKILL"]},
        )
        d = attr.to_dict()

        assert d["source"] == "capabilities"
        assert d["estimated_tokens"] == 2000
        assert d["percentage"] == 45.2
        assert d["item_count"] == 12
        assert d["metadata"] == {"types": ["TOOL", "SKILL"]}
