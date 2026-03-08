"""
Tests for codeupipe.observe module — CaptureTap, MetricsTap, RunRecord, persistence.

Verifies observability taps conform to Tap protocol, capture/export
pipeline data, and run records serialize/round-trip through JSON.
"""

import asyncio
import json

import pytest

from codeupipe.core.payload import Payload
from codeupipe.core.state import State
from codeupipe.observe import (
    CaptureTap,
    MetricsTap,
    RunRecord,
    export_captures_for_testing,
    load_run_records,
    save_run_record,
)


# ── CaptureTap ──────────────────────────────────────────────────────


class TestCaptureTap:
    """CaptureTap silently records payload snapshots."""

    @pytest.mark.unit
    def test_observe_captures_payload(self):
        tap = CaptureTap(name="test_cap")

        async def _run():
            await tap.observe(Payload({"x": 1}))
            await tap.observe(Payload({"x": 2}))

        asyncio.run(_run())
        assert len(tap.captures) == 2
        assert tap.captures[0] == {"x": 1}
        assert tap.captures[1] == {"x": 2}

    @pytest.mark.unit
    def test_max_captures_respected(self):
        tap = CaptureTap(max_captures=3)

        async def _run():
            for i in range(10):
                await tap.observe(Payload({"i": i}))

        asyncio.run(_run())
        assert len(tap.captures) == 3
        assert tap.captures[-1] == {"i": 2}

    @pytest.mark.unit
    def test_clear(self):
        tap = CaptureTap()
        asyncio.run(tap.observe(Payload({"a": 1})))
        assert len(tap.captures) == 1
        tap.clear()
        assert tap.captures == []

    @pytest.mark.unit
    def test_export_json(self):
        tap = CaptureTap()
        asyncio.run(tap.observe(Payload({"key": "val"})))
        exported = tap.export_json()
        parsed = json.loads(exported)
        assert parsed == [{"key": "val"}]

    @pytest.mark.unit
    def test_default_name(self):
        tap = CaptureTap()
        assert tap.name == "capture"


# ── MetricsTap ──────────────────────────────────────────────────────


class TestMetricsTap:
    """MetricsTap counts invocations and records timestamps."""

    @pytest.mark.unit
    def test_count_increments(self):
        tap = MetricsTap(name="m")

        async def _run():
            for _ in range(5):
                await tap.observe(Payload())

        asyncio.run(_run())
        assert tap.count == 5
        assert len(tap.timestamps) == 5

    @pytest.mark.unit
    def test_timestamps_monotonic(self):
        tap = MetricsTap()

        async def _run():
            await tap.observe(Payload())
            await tap.observe(Payload())

        asyncio.run(_run())
        assert tap.timestamps[1] >= tap.timestamps[0]

    @pytest.mark.unit
    def test_reset(self):
        tap = MetricsTap()
        asyncio.run(tap.observe(Payload()))
        tap.reset()
        assert tap.count == 0
        assert tap.timestamps == []


# ── RunRecord ───────────────────────────────────────────────────────


class TestRunRecord:
    """RunRecord captures a single pipeline execution summary."""

    @pytest.mark.unit
    def test_to_dict_round_trip(self):
        state = State()
        state.mark_executed("filter_a")
        state.mark_executed("filter_b")
        state.timings["filter_a"] = 0.05

        rec = RunRecord(
            "my_pipeline",
            state,
            input_keys=["url"],
            output_keys=["result"],
            duration=1.23,
        )
        d = rec.to_dict()

        assert d["pipeline"] == "my_pipeline"
        assert d["success"] is True
        assert d["duration"] == 1.23
        assert d["executed"] == ["filter_a", "filter_b"]
        assert d["error_count"] == 0
        assert d["input_keys"] == ["url"]
        assert d["output_keys"] == ["result"]
        assert "timestamp" in d

    @pytest.mark.unit
    def test_error_record(self):
        state = State()
        state.record_error("bad_filter", ValueError("boom"))
        rec = RunRecord("failing", state, success=False, error="boom")
        d = rec.to_dict()
        assert d["success"] is False
        assert d["error"] == "boom"
        assert d["error_count"] == 1

    @pytest.mark.unit
    def test_defaults(self):
        state = State()
        rec = RunRecord("simple", state)
        d = rec.to_dict()
        assert d["input_keys"] == []
        assert d["output_keys"] == []
        assert d["duration"] is None
        assert d["error"] is None
        assert d["success"] is True


# ── Persistence ─────────────────────────────────────────────────────


class TestRunRecordPersistence:
    """save_run_record / load_run_records round-trip through JSON files."""

    @pytest.mark.unit
    def test_save_and_load(self, tmp_path):
        runs_dir = tmp_path / "runs"
        state = State()
        state.mark_executed("a")

        rec = RunRecord("demo", state, duration=0.5)
        path = save_run_record(rec, runs_dir=runs_dir)

        assert path.exists()
        loaded = load_run_records(runs_dir=runs_dir)
        assert len(loaded) == 1
        assert loaded[0]["pipeline"] == "demo"
        assert loaded[0]["duration"] == 0.5

    @pytest.mark.unit
    def test_load_empty_dir(self, tmp_path):
        assert load_run_records(runs_dir=tmp_path) == []

    @pytest.mark.unit
    def test_load_nonexistent_dir(self, tmp_path):
        assert load_run_records(runs_dir=tmp_path / "nope") == []

    @pytest.mark.unit
    def test_pipeline_filter(self, tmp_path):
        runs_dir = tmp_path / "runs"
        for name in ("alpha", "beta", "alpha"):
            state = State()
            rec = RunRecord(name, state)
            save_run_record(rec, runs_dir=runs_dir)

        all_records = load_run_records(runs_dir=runs_dir)
        assert len(all_records) == 3

        alpha_only = load_run_records(runs_dir=runs_dir, pipeline="alpha")
        assert all(r["pipeline"] == "alpha" for r in alpha_only)
        assert len(alpha_only) == 2

    @pytest.mark.unit
    def test_limit_respected(self, tmp_path):
        runs_dir = tmp_path / "runs"
        for i in range(10):
            save_run_record(RunRecord(f"p{i}", State()), runs_dir=runs_dir)

        loaded = load_run_records(runs_dir=runs_dir, limit=3)
        assert len(loaded) == 3


# ── export_captures_for_testing ─────────────────────────────────────


class TestExportCaptures:
    """export_captures_for_testing generates valid pytest fixture files."""

    @pytest.mark.unit
    def test_generates_valid_fixture(self, tmp_path):
        captures = [{"key": "val"}, {"key": "val2"}]
        out = tmp_path / "fixtures" / "test_fixtures.py"
        result = export_captures_for_testing(captures, str(out))

        assert result.exists()
        content = result.read_text()
        assert "import pytest" in content
        assert "@pytest.fixture" in content
        assert "captured_payloads" in content
        assert '"key"' in content

    @pytest.mark.unit
    def test_custom_fixture_name(self, tmp_path):
        out = tmp_path / "fix.py"
        export_captures_for_testing([{"a": 1}], str(out), fixture_name="my_data")
        content = out.read_text()
        assert "def my_data():" in content
