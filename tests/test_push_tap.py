"""Tests for PushTap — buffered observation sink that pushes data out.

PushTap collects observations in a buffer and flushes them to a
configurable sink (callback) on a count threshold or time interval.
The sink is "just a function" — pipe into Redis, Kafka, a file, stdout,
or any external system.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from codeupipe import Payload, Pipeline, PipelineAccessor
from codeupipe.observe import PushTap


# ── Helpers ──────────────────────────────────────────────────────────


class _Passthrough:
    """Filter that passes payload through unchanged."""
    def call(self, payload):
        return payload


class _TagFilter:
    """Filter that tags the payload."""
    def call(self, payload):
        return payload.insert("tagged", True)


def _run(coro):
    return asyncio.run(coro)


def _make_recorder() -> tuple:
    """Return (sink_fn, received_list)."""
    received: List[List[Dict[str, Any]]] = []

    def sink(batch: List[Dict[str, Any]]) -> None:
        received.append(list(batch))

    return sink, received


# ── Construction ─────────────────────────────────────────────────────


class TestPushTapConstruction:
    def test_default_name(self):
        sink, _ = _make_recorder()
        tap = PushTap(sink=sink)
        assert tap.name == "push"

    def test_custom_name(self):
        sink, _ = _make_recorder()
        tap = PushTap(sink=sink, name="kafka_push")
        assert tap.name == "kafka_push"

    def test_default_threshold(self):
        sink, _ = _make_recorder()
        tap = PushTap(sink=sink)
        assert tap.threshold == 100

    def test_custom_threshold(self):
        sink, _ = _make_recorder()
        tap = PushTap(sink=sink, threshold=10)
        assert tap.threshold == 10

    def test_initial_buffer_empty(self):
        sink, _ = _make_recorder()
        tap = PushTap(sink=sink)
        assert tap.pending == 0


# ── Buffering & Threshold Flush ──────────────────────────────────────


class TestPushTapBuffering:
    def test_observe_buffers_without_flush(self):
        """Below threshold, data stays in buffer."""
        sink, received = _make_recorder()
        tap = PushTap(sink=sink, threshold=5)

        _run(tap.observe(Payload({"a": 1})))
        _run(tap.observe(Payload({"b": 2})))

        assert tap.pending == 2
        assert len(received) == 0  # Not flushed yet

    def test_threshold_triggers_flush(self):
        """When buffer hits threshold, sink is called."""
        sink, received = _make_recorder()
        tap = PushTap(sink=sink, threshold=3)

        _run(tap.observe(Payload({"a": 1})))
        _run(tap.observe(Payload({"b": 2})))
        _run(tap.observe(Payload({"c": 3})))

        assert len(received) == 1
        assert len(received[0]) == 3
        assert tap.pending == 0  # Buffer cleared after flush

    def test_flush_batch_contains_payload_dicts(self):
        """Each item in the batch is the payload.to_dict() snapshot."""
        sink, received = _make_recorder()
        tap = PushTap(sink=sink, threshold=2)

        _run(tap.observe(Payload({"x": 42})))
        _run(tap.observe(Payload({"y": 99})))

        batch = received[0]
        assert batch[0]["x"] == 42
        assert batch[1]["y"] == 99

    def test_multiple_flushes(self):
        """Buffer resets after each flush; subsequent observations start fresh."""
        sink, received = _make_recorder()
        tap = PushTap(sink=sink, threshold=2)

        for i in range(5):
            _run(tap.observe(Payload({"i": i})))

        # 5 observations / threshold 2 = 2 flushes (2+2), 1 pending
        assert len(received) == 2
        assert tap.pending == 1

    def test_flush_adds_timestamp(self):
        """Each record in the batch should have a _pushed_at timestamp."""
        sink, received = _make_recorder()
        tap = PushTap(sink=sink, threshold=1)

        _run(tap.observe(Payload({"a": 1})))

        record = received[0][0]
        assert "_pushed_at" in record
        assert isinstance(record["_pushed_at"], float)


# ── Manual Flush ─────────────────────────────────────────────────────


class TestPushTapManualFlush:
    def test_flush_sends_current_buffer(self):
        sink, received = _make_recorder()
        tap = PushTap(sink=sink, threshold=1000)  # High threshold

        _run(tap.observe(Payload({"a": 1})))
        _run(tap.observe(Payload({"b": 2})))
        tap.flush()

        assert len(received) == 1
        assert len(received[0]) == 2
        assert tap.pending == 0

    def test_flush_empty_buffer_is_noop(self):
        sink, received = _make_recorder()
        tap = PushTap(sink=sink)

        tap.flush()
        assert len(received) == 0  # No call if nothing buffered

    def test_flush_all_drains_completely(self):
        """flush() after observations leaves buffer empty."""
        sink, received = _make_recorder()
        tap = PushTap(sink=sink, threshold=1000)

        for i in range(7):
            _run(tap.observe(Payload({"i": i})))

        tap.flush()
        assert tap.pending == 0
        assert len(received[0]) == 7


# ── Stats Tracking ───────────────────────────────────────────────────


class TestPushTapStats:
    def test_total_pushed_after_flush(self):
        sink, _ = _make_recorder()
        tap = PushTap(sink=sink, threshold=3)

        for i in range(5):
            _run(tap.observe(Payload({"i": i})))

        assert tap.total_pushed == 3  # One flush of 3
        tap.flush()
        assert tap.total_pushed == 5  # Plus remaining 2

    def test_flush_count(self):
        sink, _ = _make_recorder()
        tap = PushTap(sink=sink, threshold=2)

        for i in range(7):
            _run(tap.observe(Payload({"i": i})))
        tap.flush()

        assert tap.flush_count == 4  # 3 auto + 1 manual

    def test_stats_summary(self):
        sink, _ = _make_recorder()
        tap = PushTap(sink=sink, threshold=5)

        for i in range(12):
            _run(tap.observe(Payload({"i": i})))

        stats = tap.stats()
        assert stats["name"] == "push"
        assert stats["total_observed"] == 12
        assert stats["total_pushed"] == 10  # 2 flushes of 5
        assert stats["pending"] == 2
        assert stats["flush_count"] == 2
        assert stats["threshold"] == 5

    def test_reset_clears_everything(self):
        sink, _ = _make_recorder()
        tap = PushTap(sink=sink, threshold=2)

        for i in range(5):
            _run(tap.observe(Payload({"i": i})))

        tap.reset()
        assert tap.pending == 0
        assert tap.total_pushed == 0
        assert tap.flush_count == 0

        stats = tap.stats()
        assert stats["total_observed"] == 0


# ── Sink Error Handling ──────────────────────────────────────────────


class TestPushTapSinkErrors:
    def test_sink_exception_does_not_lose_data(self):
        """If sink raises, buffer is NOT cleared — data preserved."""
        calls = []

        def bad_sink(batch):
            calls.append(len(batch))
            raise ConnectionError("redis down")

        tap = PushTap(sink=bad_sink, threshold=2)

        _run(tap.observe(Payload({"a": 1})))
        _run(tap.observe(Payload({"b": 2})))

        # Sink was called but raised — buffer should still have the data
        assert len(calls) == 1
        assert tap.pending == 2  # Data preserved on failure

    def test_retry_after_sink_recovers(self):
        """After a sink failure, next flush retries the buffered data."""
        attempt = [0]
        received: List[list] = []

        def flaky_sink(batch):
            attempt[0] += 1
            if attempt[0] == 1:
                raise ConnectionError("temporary failure")
            received.append(list(batch))

        tap = PushTap(sink=flaky_sink, threshold=2)

        _run(tap.observe(Payload({"a": 1})))
        _run(tap.observe(Payload({"b": 2})))
        # First flush failed — data preserved
        assert tap.pending == 2

        # Manual flush — should succeed now
        tap.flush()
        assert tap.pending == 0
        assert len(received) == 1
        assert len(received[0]) == 2


# ── Pipeline Integration ─────────────────────────────────────────────


class TestPushTapPipelineIntegration:
    def test_push_tap_with_pipeline(self):
        """PushTap works as a real pipeline tap."""
        sink, received = _make_recorder()
        tap = PushTap(sink=sink, threshold=3)

        pipe = Pipeline()
        pipe.add_filter(_TagFilter(), name="tagger")
        pipe.add_tap(tap, name="push_out")

        for i in range(3):
            _run(pipe.run(Payload({"i": i})))

        assert len(received) == 1
        assert all("tagged" in r for r in received[0])

    def test_push_tap_with_pipeline_accessor(self):
        """PipelineAccessor can attach PushTap to multiple pipelines."""
        sink, received = _make_recorder()
        tap = PushTap(sink=sink, threshold=2)

        pipe_a = Pipeline()
        pipe_a.add_filter(_Passthrough(), name="a")
        pipe_b = Pipeline()
        pipe_b.add_filter(_Passthrough(), name="b")

        acc = PipelineAccessor(pipe_a, pipe_b)
        acc.add_tap(tap, "push_out")

        _run(pipe_a.run(Payload({"from": "a"})))
        _run(pipe_b.run(Payload({"from": "b"})))

        # 2 observations = threshold met
        assert len(received) == 1
        sources = {r.get("from") for r in received[0]}
        assert sources == {"a", "b"}

    def test_flush_on_shutdown(self):
        """Demonstrates the pattern: flush remaining on server shutdown."""
        sink, received = _make_recorder()
        tap = PushTap(sink=sink, threshold=1000)

        pipe = Pipeline()
        pipe.add_filter(_Passthrough(), name="p")
        pipe.add_tap(tap, name="push_out")

        _run(pipe.run(Payload({"req": 1})))
        _run(pipe.run(Payload({"req": 2})))

        assert len(received) == 0  # Below threshold
        tap.flush()  # Shutdown drain
        assert len(received) == 1
        assert len(received[0]) == 2


# ── Built-in Sinks ──────────────────────────────────────────────────


class TestBuiltInSinks:
    def test_file_sink(self, tmp_path):
        from codeupipe.observe import file_sink

        path = tmp_path / "pushed.jsonl"
        sink = file_sink(str(path))
        tap = PushTap(sink=sink, threshold=2)

        _run(tap.observe(Payload({"a": 1})))
        _run(tap.observe(Payload({"b": 2})))

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["a"] == 1
        assert json.loads(lines[1])["b"] == 2

    def test_file_sink_appends(self, tmp_path):
        from codeupipe.observe import file_sink

        path = tmp_path / "pushed.jsonl"
        sink = file_sink(str(path))
        tap = PushTap(sink=sink, threshold=1)

        _run(tap.observe(Payload({"first": True})))
        _run(tap.observe(Payload({"second": True})))

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_stdout_sink(self, capsys):
        from codeupipe.observe import stdout_sink

        tap = PushTap(sink=stdout_sink, threshold=1)
        _run(tap.observe(Payload({"hello": "world"})))

        captured = capsys.readouterr()
        assert "hello" in captured.out
        assert "world" in captured.out
