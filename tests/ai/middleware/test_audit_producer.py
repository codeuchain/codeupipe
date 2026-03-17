"""Tests for AuditProducer implementations."""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from codeupipe.ai.hooks.audit_event import AuditEvent
from codeupipe.ai.hooks.audit_producer import (
    CompositeAuditProducer,
    FileAuditSink,
    LogAuditSink,
    NoopAuditSink,
)


def _make_event(**overrides) -> AuditEvent:
    """Factory for test events."""
    defaults = {
        "timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "session_id": "test-session",
        "loop_iteration": 1,
        "link_name": "test_link",
        "input_keys": ("a", "b"),
        "output_keys": ("a", "b", "c"),
        "duration_ms": 42.0,
    }
    defaults.update(overrides)
    return AuditEvent(**defaults)


@pytest.mark.unit
class TestNoopAuditSink:
    """NoopAuditSink discards events silently."""

    @pytest.mark.asyncio
    async def test_send_does_nothing(self):
        sink = NoopAuditSink()
        await sink.send(_make_event())  # no crash


@pytest.mark.unit
class TestLogAuditSink:
    """LogAuditSink writes to Python logging."""

    @pytest.mark.asyncio
    async def test_send_logs(self, caplog):
        sink = LogAuditSink(level=20)  # INFO
        event = _make_event(link_name="send_turn", duration_ms=100.5)

        with caplog.at_level(20, logger="codeupipe.ai.hooks.audit"):
            await sink.send(event)

        assert "send_turn" in caplog.text
        assert "100.5ms" in caplog.text

    @pytest.mark.asyncio
    async def test_send_with_error(self, caplog):
        sink = LogAuditSink(level=20)
        event = _make_event(error="Timeout")

        with caplog.at_level(20, logger="codeupipe.ai.hooks.audit"):
            await sink.send(event)

        assert "error=Timeout" in caplog.text


@pytest.mark.unit
class TestFileAuditSink:
    """FileAuditSink appends JSON lines."""

    @pytest.mark.asyncio
    async def test_write_jsonl(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        sink = FileAuditSink(path)

        await sink.send(_make_event(link_name="link_a"))
        await sink.send(_make_event(link_name="link_b"))

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2

        first = json.loads(lines[0])
        assert first["link_name"] == "link_a"

        second = json.loads(lines[1])
        assert second["link_name"] == "link_b"

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "audit.jsonl"
        sink = FileAuditSink(path)
        await sink.send(_make_event())
        assert path.exists()


@pytest.mark.unit
class TestCompositeAuditProducer:
    """CompositeAuditProducer fans out to multiple sinks."""

    @pytest.mark.asyncio
    async def test_fans_out(self, tmp_path):
        file_a = tmp_path / "a.jsonl"
        file_b = tmp_path / "b.jsonl"

        composite = CompositeAuditProducer([
            FileAuditSink(file_a),
            FileAuditSink(file_b),
        ])

        await composite.send(_make_event())

        assert file_a.exists()
        assert file_b.exists()
        assert len(file_a.read_text().strip().split("\n")) == 1
        assert len(file_b.read_text().strip().split("\n")) == 1

    @pytest.mark.asyncio
    async def test_one_sink_failure_doesnt_block_others(self, tmp_path):
        """If one sink fails, others still receive the event."""
        file_path = tmp_path / "good.jsonl"

        class BadSink(NoopAuditSink):
            async def send(self, event):
                raise RuntimeError("broken")

        composite = CompositeAuditProducer([
            BadSink(),
            FileAuditSink(file_path),
        ])

        await composite.send(_make_event())

        # Good sink still received the event
        assert file_path.exists()
