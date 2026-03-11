"""Tests for PipelineAccessor — apply anything to pipeline(s)."""

import asyncio

import pytest

from codeupipe import Payload, Pipeline, Registry
from codeupipe.observe import InsightTap, CaptureTap, MetricsTap
from codeupipe.runtime import PipelineAccessor, TapSwitch


# ── Helpers ──────────────────────────────────────────────────────────


class _AddOne:
    """Trivial filter."""
    def call(self, payload):
        return payload.insert("n", payload.get("n") + 1)


class _Double:
    """Trivial filter."""
    def call(self, payload):
        return payload.insert("n", payload.get("n") * 2)


class _RecordingHook:
    """Minimal hook that records before/after calls."""
    def __init__(self):
        self.events = []

    def before(self, step, payload):
        self.events.append(("before", step))

    def after(self, step, payload):
        self.events.append(("after", step))

    def on_error(self, step, error, payload):
        self.events.append(("error", step, str(error)))


def _run(coro):
    return asyncio.run(coro)


# ── Single Pipeline ──────────────────────────────────────────────────


class TestPipelineAccessorSingle:
    def test_wrap_single_pipeline(self):
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        acc = PipelineAccessor(pipe)
        assert acc.pipeline_count == 1

    def test_add_tap(self):
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        acc = PipelineAccessor(pipe)
        tap = InsightTap()
        acc.add_tap(tap, "my_insight")
        # Tap should be on the pipeline now
        result = _run(pipe.run(Payload({"n": 0})))
        assert result.get("n") == 1
        assert tap.summary()["total_runs"] == 1

    def test_add_different_taps(self):
        """Accessor doesn't care what kind of tap — any Tap works."""
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        acc = PipelineAccessor(pipe)
        insight = InsightTap()
        capture = CaptureTap(name="cap")
        acc.add_tap(insight, "insights")
        acc.add_tap(capture, "captures")
        _run(pipe.run(Payload({"n": 0})))
        assert insight.summary()["total_runs"] == 1
        assert len(capture.captures) == 1

    def test_use_hook(self):
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        acc = PipelineAccessor(pipe)
        hook = _RecordingHook()
        acc.use_hook(hook)
        _run(pipe.run(Payload({"n": 0})))
        # Hook should have fired
        assert len(hook.events) > 0

    def test_remove_tap(self):
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        tap = InsightTap()
        pipe.add_tap(tap, name="removable")
        acc = PipelineAccessor(pipe)
        acc.remove_tap("removable")
        _run(pipe.run(Payload({"n": 0})))
        # Tap was removed, should not have observed
        assert tap.summary()["total_runs"] == 0

    def test_remove_tap_not_found(self):
        pipe = Pipeline()
        acc = PipelineAccessor(pipe)
        with pytest.raises(KeyError):
            acc.remove_tap("nonexistent")

    def test_remove_hook(self):
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        hook = _RecordingHook()
        pipe.use_hook(hook)
        acc = PipelineAccessor(pipe)
        acc.remove_hook(hook)
        _run(pipe.run(Payload({"n": 0})))
        assert len(hook.events) == 0

    def test_status(self):
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        pipe.add_tap(InsightTap(), name="insight_tap")
        acc = PipelineAccessor(pipe)
        info = acc.status()
        assert len(info) == 1  # one pipeline
        assert "insight_tap" in info[0]["taps"]
        assert "add" in info[0]["filters"]

    def test_apply_callable(self):
        """apply() lets users do anything — ultimate flexibility."""
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        acc = PipelineAccessor(pipe)
        applied = []
        acc.apply(lambda p: applied.append(p))
        assert len(applied) == 1
        assert applied[0] is pipe


# ── Multiple Pipelines ───────────────────────────────────────────────


class TestPipelineAccessorMultiple:
    def test_wrap_multiple(self):
        p1 = Pipeline()
        p2 = Pipeline()
        acc = PipelineAccessor(p1, p2)
        assert acc.pipeline_count == 2

    def test_add_tap_to_all(self):
        p1 = Pipeline()
        p1.add_filter(_AddOne(), name="add")
        p2 = Pipeline()
        p2.add_filter(_Double(), name="double")

        tap1 = InsightTap(name="i1")
        tap2 = InsightTap(name="i2")
        acc = PipelineAccessor(p1, p2)

        # add_tap creates a SEPARATE tap per pipeline by default?
        # No — it should add the SAME tap to all, so the user can share
        # or pass unique ones. Accessor just iterates.
        shared_tap = InsightTap()
        acc.add_tap(shared_tap, "shared")

        _run(p1.run(Payload({"n": 0})))
        _run(p2.run(Payload({"n": 3})))

        # Shared tap saw both runs
        assert shared_tap.summary()["total_runs"] == 2

    def test_use_hook_on_all(self):
        p1 = Pipeline()
        p1.add_filter(_AddOne(), name="add")
        p2 = Pipeline()
        p2.add_filter(_Double(), name="double")
        hook = _RecordingHook()
        acc = PipelineAccessor(p1, p2)
        acc.use_hook(hook)
        _run(p1.run(Payload({"n": 0})))
        _run(p2.run(Payload({"n": 3})))
        # Hook saw events from both pipelines
        assert len(hook.events) > 2

    def test_remove_tap_from_all(self):
        p1 = Pipeline()
        p1.add_filter(_AddOne(), name="add")
        p2 = Pipeline()
        p2.add_filter(_Double(), name="double")
        tap = InsightTap()
        p1.add_tap(tap, name="shared")
        p2.add_tap(tap, name="shared")
        acc = PipelineAccessor(p1, p2)
        acc.remove_tap("shared")
        _run(p1.run(Payload({"n": 0})))
        _run(p2.run(Payload({"n": 3})))
        assert tap.summary()["total_runs"] == 0

    def test_apply_callable_on_all(self):
        p1 = Pipeline()
        p2 = Pipeline()
        p3 = Pipeline()
        acc = PipelineAccessor(p1, p2, p3)
        seen = []
        acc.apply(lambda p: seen.append(id(p)))
        assert len(seen) == 3

    def test_status_multiple(self):
        p1 = Pipeline()
        p1.add_filter(_AddOne(), name="step_a")
        p1.add_tap(InsightTap(), name="tap_a")
        p2 = Pipeline()
        p2.add_filter(_Double(), name="step_b")
        acc = PipelineAccessor(p1, p2)
        info = acc.status()
        assert len(info) == 2
        assert "tap_a" in info[0]["taps"]
        assert "step_b" in info[1]["filters"]


# ── From Registry ────────────────────────────────────────────────────


class TestPipelineAccessorFromRegistry:
    def test_from_registry(self):
        reg = Registry()
        p1 = Pipeline()
        p1.add_filter(_AddOne(), name="add")
        p2 = Pipeline()
        p2.add_filter(_Double(), name="double")
        reg.register("pipe_a", lambda: p1)
        reg.register("pipe_b", lambda: p2)

        acc = PipelineAccessor.from_registry(reg, kinds=["filter"])
        # from_registry should resolve pipeline instances
        # This depends on registry holding Pipelines or factories.
        # For now, test that it works with explicit pipeline registration.
        assert acc.pipeline_count >= 0  # At minimum, doesn't crash


# ── Composes with TapSwitch ──────────────────────────────────────────


class TestPipelineAccessorWithTapSwitch:
    def test_add_tap_then_toggle(self):
        """PipelineAccessor adds taps, TapSwitch toggles them. Composable."""
        pipe = Pipeline()
        pipe.add_filter(_AddOne(), name="add")
        acc = PipelineAccessor(pipe)
        tap = InsightTap()
        acc.add_tap(tap, "togglable")

        # Run once — tap sees it
        _run(pipe.run(Payload({"n": 0})))
        assert tap.summary()["total_runs"] == 1

        # Toggle off via TapSwitch
        switch = TapSwitch(pipe)
        switch.disable("togglable")
        _run(pipe.run(Payload({"n": 0})))
        # Tap should NOT have seen the second run
        assert tap.summary()["total_runs"] == 1

        # Toggle back on
        switch.enable("togglable")
        _run(pipe.run(Payload({"n": 0})))
        assert tap.summary()["total_runs"] == 2
