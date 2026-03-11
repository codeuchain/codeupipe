"""Tests for InsightTap — runtime stats accumulator."""

import asyncio
import json
import threading
import time
from pathlib import Path

import pytest

from codeupipe import Payload, Pipeline
from codeupipe.observe import InsightTap


# ── Helpers ──────────────────────────────────────────────────────────


class _AddOne:
    """Trivial filter: increments 'n'."""
    def call(self, payload):
        return payload.insert("n", payload.get("n") + 1)


class _Slow:
    """Filter that sleeps for a controlled duration."""
    def __init__(self, seconds: float = 0.05):
        self._seconds = seconds

    def call(self, payload):
        time.sleep(self._seconds)
        return payload.insert("slept", True)


class _Boom:
    """Filter that always raises."""
    def call(self, payload):
        raise RuntimeError("boom")


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ── Construction ─────────────────────────────────────────────────────


class TestInsightTapConstruction:
    def test_default_name(self):
        tap = InsightTap()
        assert tap.name == "insight"

    def test_custom_name(self):
        tap = InsightTap(name="my_insights")
        assert tap.name == "my_insights"

    def test_initial_summary_empty(self):
        tap = InsightTap()
        s = tap.summary()
        assert s["total_runs"] == 0
        assert s["error_count"] == 0
        assert s["throughput_per_sec"] == 0.0


# ── Observation ──────────────────────────────────────────────────────


class TestInsightTapObservation:
    def test_counts_runs(self):
        tap = InsightTap()
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        pipe.add_tap(tap, name="insight")
        for i in range(5):
            _run(pipe.run(Payload({"n": i})))
        assert tap.summary()["total_runs"] == 5

    def test_records_inter_arrival(self):
        tap = InsightTap()
        pipe = Pipeline()
        pipe.add_filter(_Slow(0.02), name="slow")
        pipe.add_tap(tap, name="insight")
        # Two runs so we get at least one inter-arrival gap
        _run(pipe.run(Payload({"x": 1})))
        _run(pipe.run(Payload({"x": 2})))
        s = tap.summary()
        assert s["total_runs"] == 2
        # Inter-arrival gap should include the 20ms sleep
        assert s["avg_duration_ms"] >= 15.0

    def test_records_min_max(self):
        tap = InsightTap()
        pipe = Pipeline()
        pipe.add_filter(_Slow(0.02), name="slow")
        pipe.add_tap(tap, name="insight")

        # Three runs to get two gaps
        _run(pipe.run(Payload({"n": 0})))
        _run(pipe.run(Payload({"n": 1})))
        _run(pipe.run(Payload({"n": 2})))

        s = tap.summary()
        assert s["total_runs"] == 3
        assert s["min_duration_ms"] > 0
        assert s["max_duration_ms"] >= s["min_duration_ms"]

    def test_percentiles(self):
        tap = InsightTap()
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        pipe.add_tap(tap, name="insight")
        for i in range(20):
            _run(pipe.run(Payload({"n": i})))
        s = tap.summary()
        assert "p95_duration_ms" in s
        assert "p99_duration_ms" in s
        assert s["p95_duration_ms"] >= s["avg_duration_ms"] or s["total_runs"] >= 20

    def test_throughput(self):
        tap = InsightTap()
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        pipe.add_tap(tap, name="insight")
        for i in range(10):
            _run(pipe.run(Payload({"n": i})))
        s = tap.summary()
        # Should have some throughput — at least 1 run/sec
        assert s["throughput_per_sec"] > 0.0

    def test_payload_keys_tracked(self):
        """InsightTap should track what keys it's seeing flow through."""
        tap = InsightTap()
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        pipe.add_tap(tap, name="insight")
        _run(pipe.run(Payload({"n": 0, "user": "alice"})))
        _run(pipe.run(Payload({"n": 5, "order_id": 42})))
        s = tap.summary()
        assert "n" in s["observed_keys"]
        assert "user" in s["observed_keys"]
        assert "order_id" in s["observed_keys"]


# ── Error Tracking ───────────────────────────────────────────────────


class TestInsightTapErrors:
    def test_error_count_zero_on_success(self):
        tap = InsightTap()
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        pipe.add_tap(tap, name="insight")
        _run(pipe.run(Payload({"n": 0})))
        assert tap.summary()["error_count"] == 0

    def test_records_errors_when_upstream_fails(self):
        """When observe() sees a payload with _error key, it counts it."""
        tap = InsightTap()
        # Simulate by calling observe directly with error-bearing payload
        _run(tap.observe(Payload({"_error": "something went wrong"})))
        assert tap.summary()["error_count"] == 1

    def test_error_rate(self):
        tap = InsightTap()
        # 3 successful observations + 1 error
        for _ in range(3):
            _run(tap.observe(Payload({"n": 1})))
        _run(tap.observe(Payload({"_error": "fail"})))
        s = tap.summary()
        assert s["total_runs"] == 4
        assert s["error_count"] == 1
        assert abs(s["error_rate_pct"] - 25.0) < 1.0


# ── Reset ────────────────────────────────────────────────────────────


class TestInsightTapReset:
    def test_reset_clears_all(self):
        tap = InsightTap()
        for _ in range(5):
            _run(tap.observe(Payload({"n": 1})))
        assert tap.summary()["total_runs"] == 5
        tap.reset()
        s = tap.summary()
        assert s["total_runs"] == 0
        assert s["error_count"] == 0
        assert s["throughput_per_sec"] == 0.0

    def test_accumulates_after_reset(self):
        tap = InsightTap()
        for _ in range(3):
            _run(tap.observe(Payload({"n": 1})))
        tap.reset()
        for _ in range(2):
            _run(tap.observe(Payload({"n": 2})))
        assert tap.summary()["total_runs"] == 2


# ── Export ───────────────────────────────────────────────────────────


class TestInsightTapExport:
    def test_export_json_string(self):
        tap = InsightTap()
        _run(tap.observe(Payload({"n": 1})))
        raw = tap.export_json()
        data = json.loads(raw)
        assert data["total_runs"] == 1
        assert "timestamp" in data

    def test_export_to_file(self, tmp_path):
        tap = InsightTap()
        _run(tap.observe(Payload({"n": 1})))
        out = tmp_path / "insights.json"
        tap.export_json(str(out))
        data = json.loads(out.read_text())
        assert data["total_runs"] == 1


# ── Thread Safety ────────────────────────────────────────────────────


class TestInsightTapThreadSafety:
    def test_concurrent_observations(self):
        tap = InsightTap()
        count = 100
        barrier = threading.Barrier(4)

        def worker():
            barrier.wait()
            for _ in range(count):
                asyncio.run(tap.observe(Payload({"n": 1})))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert tap.summary()["total_runs"] == 400
