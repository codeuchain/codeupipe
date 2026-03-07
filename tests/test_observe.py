"""Tests for Ring 4 — Observe features.

Covers: timing, lineage, trace ID, events, describe(), State.diff().
"""

import asyncio
import pytest
from codeupipe.core.payload import Payload
from codeupipe.core.pipeline import Pipeline
from codeupipe.core.state import State
from codeupipe.core.event import PipelineEvent, EventEmitter


# ── Helpers ──────────────────────────────────────────────────

class AddFilter:
    async def call(self, payload: Payload) -> Payload:
        return payload.insert("value", payload.get("value", 0) + 10)


class MultiplyFilter:
    async def call(self, payload: Payload) -> Payload:
        return payload.insert("value", payload.get("value", 0) * 2)


class FailFilter:
    async def call(self, payload: Payload) -> Payload:
        raise ValueError("intentional failure")


class LogTap:
    def __init__(self):
        self.seen = []

    async def observe(self, payload: Payload) -> None:
        self.seen.append(payload.get("value"))


class TrackingHook:
    def __init__(self):
        self.calls = []

    async def before(self, filter, payload):
        self.calls.append(("before", filter.__class__.__name__ if filter else "pipeline"))

    async def after(self, filter, payload):
        self.calls.append(("after", filter.__class__.__name__ if filter else "pipeline"))

    async def on_error(self, filter, error, payload):
        self.calls.append(("error", str(error)))


# ── Timing ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timing_recorded_in_state():
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.add_filter(MultiplyFilter(), name="multiply")
    pipe.observe(timing=True)

    await pipe.run(Payload({"value": 5}))

    assert "add" in pipe.state.timings
    assert "multiply" in pipe.state.timings
    assert pipe.state.timings["add"] >= 0
    assert pipe.state.timings["multiply"] >= 0


@pytest.mark.asyncio
async def test_timing_not_recorded_without_observe():
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")

    await pipe.run(Payload({"value": 5}))

    assert len(pipe.state.timings) == 0


@pytest.mark.asyncio
async def test_timing_includes_all_step_types():
    inner = Pipeline()
    inner.add_filter(AddFilter(), name="inner_add")

    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.add_parallel([AddFilter(), MultiplyFilter()], name="par")
    pipe.add_pipeline(inner, name="nested")
    pipe.observe(timing=True)

    await pipe.run(Payload({"value": 5}))

    assert "add" in pipe.state.timings
    assert "par" in pipe.state.timings
    assert "nested" in pipe.state.timings


@pytest.mark.asyncio
async def test_timing_records_on_error():
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.add_filter(FailFilter(), name="fail")
    pipe.observe(timing=True)

    with pytest.raises(ValueError):
        await pipe.run(Payload({"value": 5}))

    assert "add" in pipe.state.timings
    assert "fail" in pipe.state.timings


# ── Lineage ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lineage_tracks_steps():
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="step_a")
    pipe.add_filter(MultiplyFilter(), name="step_b")
    pipe.observe(lineage=True)

    result = await pipe.run(Payload({"value": 1}))

    assert result.lineage == ["step_a", "step_b"]


@pytest.mark.asyncio
async def test_lineage_not_tracked_without_observe():
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")

    result = await pipe.run(Payload({"value": 1}))

    assert result.lineage == []


def test_payload_trace_id_with_trace():
    p = Payload({"x": 1}).with_trace("trace-abc")
    assert p.trace_id == "trace-abc"
    assert p.get("x") == 1


def test_trace_id_propagates_through_insert():
    p = Payload({"x": 1}, trace_id="t1")
    p2 = p.insert("y", 2)
    assert p2.trace_id == "t1"


def test_trace_id_propagates_through_merge():
    p1 = Payload({"a": 1}, trace_id="t1")
    p2 = Payload({"b": 2})
    merged = p1.merge(p2)
    assert merged.trace_id == "t1"


def test_lineage_propagates_through_insert():
    p = Payload({"x": 1}, _lineage=["step_a"])
    p2 = p.insert("y", 2)
    assert p2.lineage == ["step_a"]


def test_lineage_propagates_through_merge():
    p1 = Payload({"a": 1}, _lineage=["s1"])
    p2 = Payload({"b": 2}, _lineage=["s2"])
    merged = p1.merge(p2)
    assert merged.lineage == ["s1", "s2"]


def test_mutable_payload_preserves_trace():
    p = Payload({"x": 1}, trace_id="t1", _lineage=["a"])
    m = p.with_mutation()
    assert m.trace_id == "t1"
    assert m.lineage == ["a"]
    back = m.to_immutable()
    assert back.trace_id == "t1"
    assert back.lineage == ["a"]


# ── Events ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_events_step_start_end():
    events = []
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.on("step.start", lambda e: events.append(e))
    pipe.on("step.end", lambda e: events.append(e))

    await pipe.run(Payload({"value": 1}))

    kinds = [e.kind for e in events]
    assert "step.start" in kinds
    assert "step.end" in kinds
    start_ev = [e for e in events if e.kind == "step.start"][0]
    assert start_ev.step_name == "add"
    end_ev = [e for e in events if e.kind == "step.end"][0]
    assert end_ev.step_name == "add"
    assert end_ev.duration is not None
    assert end_ev.duration >= 0


@pytest.mark.asyncio
async def test_events_pipeline_start_end():
    events = []
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.on("pipeline.start", lambda e: events.append(e))
    pipe.on("pipeline.end", lambda e: events.append(e))

    await pipe.run(Payload({"value": 1}))

    kinds = [e.kind for e in events]
    assert kinds == ["pipeline.start", "pipeline.end"]


@pytest.mark.asyncio
async def test_events_step_error():
    events = []
    pipe = Pipeline()
    pipe.add_filter(FailFilter(), name="fail")
    pipe.on("step.error", lambda e: events.append(e))

    with pytest.raises(ValueError):
        await pipe.run(Payload({"value": 1}))

    assert len(events) == 1
    assert events[0].step_name == "fail"
    assert events[0].error is not None


@pytest.mark.asyncio
async def test_events_wildcard_listener():
    events = []
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.on("*", lambda e: events.append(e.kind))

    await pipe.run(Payload({"value": 1}))

    assert "pipeline.start" in events
    assert "step.start" in events
    assert "step.end" in events
    assert "pipeline.end" in events


@pytest.mark.asyncio
async def test_events_on_off():
    events = []
    handler = lambda e: events.append(e.kind)
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.on("step.end", handler)
    pipe.off("step.end", handler)

    await pipe.run(Payload({"value": 1}))

    assert "step.end" not in events


@pytest.mark.asyncio
async def test_events_async_listener():
    events = []

    async def handler(event):
        events.append(event.kind)

    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.on("step.end", handler)

    await pipe.run(Payload({"value": 1}))

    assert "step.end" in events


@pytest.mark.asyncio
async def test_events_retry_emit():
    events = []

    class AlwaysFail:
        async def call(self, payload):
            raise RuntimeError("boom")

    pipe = Pipeline()
    pipe.add_filter(AlwaysFail(), name="fail")
    pipe.on("pipeline.retry", lambda e: events.append(e))

    wrapped = pipe.with_retry(max_retries=2)

    with pytest.raises(RuntimeError):
        await wrapped.run(Payload({}))

    assert len(events) == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_events_circuit_open_emit():
    events = []

    class AlwaysFail:
        async def call(self, payload):
            raise RuntimeError("boom")

    pipe = Pipeline()
    pipe.add_filter(AlwaysFail(), name="fail")
    pipe.on("circuit.open", lambda e: events.append(e))

    wrapped = pipe.with_circuit_breaker(failure_threshold=2)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await wrapped.run(Payload({}))

    from codeupipe.core.pipeline import CircuitOpenError
    with pytest.raises(CircuitOpenError):
        await wrapped.run(Payload({}))

    assert len(events) == 1
    assert events[0].kind == "circuit.open"


@pytest.mark.asyncio
async def test_events_carry_trace_id():
    events = []
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.on("step.start", lambda e: events.append(e))

    await pipe.run(Payload({"value": 1}, trace_id="trace-xyz"))

    assert events[0].trace_id == "trace-xyz"


# ── Describe ─────────────────────────────────────────────────

def test_describe_simple_pipeline():
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.add_filter(MultiplyFilter(), name="multiply")

    desc = pipe.describe()

    assert desc["step_count"] == 2
    assert desc["steps"][0]["name"] == "add"
    assert desc["steps"][0]["type"] == "filter"
    assert desc["steps"][1]["name"] == "multiply"


def test_describe_parallel_pipeline():
    pipe = Pipeline()
    pipe.add_parallel([AddFilter(), MultiplyFilter()], name="par_group")

    desc = pipe.describe()

    assert desc["step_count"] == 1
    assert desc["steps"][0]["type"] == "parallel"
    assert len(desc["steps"][0]["filters"]) == 2


def test_describe_nested_pipeline():
    inner = Pipeline()
    inner.add_filter(AddFilter(), name="inner_add")

    outer = Pipeline()
    outer.add_filter(MultiplyFilter(), name="outer_mul")
    outer.add_pipeline(inner, name="nested")

    desc = outer.describe()

    assert desc["step_count"] == 2
    nested_step = desc["steps"][1]
    assert nested_step["type"] == "pipeline"
    assert len(nested_step["children"]) == 1
    assert nested_step["children"][0]["name"] == "inner_add"


def test_describe_empty_pipeline():
    pipe = Pipeline()

    desc = pipe.describe()

    assert desc["step_count"] == 0
    assert desc["steps"] == []


def test_describe_with_hooks():
    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add")
    pipe.use_hook(TrackingHook())

    desc = pipe.describe()

    assert "TrackingHook" in desc["hooks"]


def test_describe_with_tap():
    pipe = Pipeline()
    tap = LogTap()
    pipe.add_tap(tap, name="log")

    desc = pipe.describe()

    assert desc["steps"][0]["type"] == "tap"
    assert desc["steps"][0]["name"] == "log"


# ── State Diff ───────────────────────────────────────────────

def test_state_diff_added_steps():
    s1 = State()
    s1.mark_executed("a")

    s2 = State()
    s2.mark_executed("a")
    s2.mark_executed("b")

    diff = s1.diff(s2)

    assert diff["added_steps"] == ["b"]


def test_state_diff_removed_steps():
    s1 = State()
    s1.mark_executed("a")
    s1.mark_executed("b")

    s2 = State()
    s2.mark_executed("a")

    diff = s1.diff(s2)

    assert diff["removed_steps"] == ["b"]


def test_state_diff_timing_changes():
    s1 = State()
    s1.record_timing("step_a", 0.5)

    s2 = State()
    s2.record_timing("step_a", 1.2)

    diff = s1.diff(s2)

    assert "timing_changes" in diff
    assert diff["timing_changes"]["step_a"]["old"] == 0.5
    assert diff["timing_changes"]["step_a"]["new"] == 1.2


def test_state_diff_no_changes():
    s1 = State()
    s1.mark_executed("a")

    s2 = State()
    s2.mark_executed("a")

    diff = s1.diff(s2)

    assert diff == {}


def test_state_diff_error_changes():
    s1 = State()

    s2 = State()
    s2.record_error("step_x", ValueError("oops"))

    diff = s1.diff(s2)

    assert "error_changes" in diff
    assert "step_x" in diff["error_changes"]["added"]


def test_state_timings_in_repr():
    s = State()
    s.mark_executed("a")
    s.record_timing("a", 0.1)

    r = repr(s)
    assert "timings=1" in r


def test_state_reset_clears_timings():
    s = State()
    s.record_timing("a", 0.5)
    s.reset()

    assert s.timings == {}


# ── from_config observe support ──────────────────────────────

@pytest.mark.asyncio
async def test_from_config_observe_timing(tmp_path):
    from codeupipe import Registry

    reg = Registry()

    class AddTen:
        async def call(self, payload):
            return payload.insert("value", payload.get("value", 0) + 10)

    reg.register("AddTen", AddTen)

    config = tmp_path / "pipe.json"
    import json
    config.write_text(json.dumps({
        "pipeline": {
            "observe": {"timing": True},
            "steps": [{"name": "AddTen", "type": "filter"}],
        }
    }))

    pipe = Pipeline.from_config(str(config), registry=reg)
    result = await pipe.run(Payload({"value": 0}))

    assert result.get("value") == 10
    assert "AddTen" in pipe.state.timings


@pytest.mark.asyncio
async def test_from_config_observe_lineage(tmp_path):
    from codeupipe import Registry

    reg = Registry()

    class StepA:
        async def call(self, payload):
            return payload.insert("a", True)

    class StepB:
        async def call(self, payload):
            return payload.insert("b", True)

    reg.register("StepA", StepA)
    reg.register("StepB", StepB)

    config = tmp_path / "pipe.json"
    import json
    config.write_text(json.dumps({
        "pipeline": {
            "observe": {"timing": True, "lineage": True},
            "steps": [
                {"name": "StepA", "type": "filter"},
                {"name": "StepB", "type": "filter"},
            ],
        }
    }))

    pipe = Pipeline.from_config(str(config), registry=reg)
    result = await pipe.run(Payload({}))

    assert result.lineage == ["StepA", "StepB"]
    assert len(pipe.state.timings) == 2


# ── EventEmitter unit tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_emitter_off_nonexistent_callback():
    """Removing a callback that was never registered should not error."""
    emitter = EventEmitter()
    emitter.off("step.start", lambda e: None)  # no-op


@pytest.mark.asyncio
async def test_emitter_multiple_listeners():
    results = []
    emitter = EventEmitter()
    emitter.on("test", lambda e: results.append("a"))
    emitter.on("test", lambda e: results.append("b"))

    await emitter.emit(PipelineEvent(kind="test"))

    assert results == ["a", "b"]
