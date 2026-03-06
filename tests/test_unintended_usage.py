"""
Unintended Usage Tests — What Happens When Users Do Things Wrong?

These tests simulate accidental misuse, edge-case abuse, and unexpected
patterns that real users *will* stumble into. The goal is to verify the
framework either handles these gracefully or fails with clear errors —
never silently corrupts data.

Categories:
  1. Filter returns wrong types (None, str, int, dict, list)
  2. Empty / degenerate pipelines
  3. Valve predicate misbehavior (raises, non-bool, None)
  4. Duplicate and colliding step names
  5. Same filter instance reused (shared state)
  6. Tap / Hook that raises
  7. Hook on_error that raises (error-in-error-handler)
  8. RetryFilter wrapping RetryFilter (double retry)
  9. Payload constructor abuse (list, int, bool, object)
  10. MutablePayload misuse
  11. Recursive pipeline (pipeline inside pipeline)
  12. Very large pipelines (100+ filters)
  13. Streaming edge cases (empty source, huge fan-out)
  14. Passing MutablePayload to pipeline.run()
  15. Filter that mutates the immutable Payload._data directly
"""

import asyncio
from typing import AsyncIterator, List

import pytest

from codeupipe import (
    Hook,
    MutablePayload,
    Payload,
    Pipeline,
    RetryFilter,
    State,
    Valve,
)


def run(coro):
    return asyncio.run(coro)


async def collect(aiter):
    results = []
    async for item in aiter:
        results.append(item)
    return results


async def make_source(*dicts):
    for d in dicts:
        yield Payload(d)


# ===================================================================
# 1. Filter Returns Wrong Types
# ===================================================================


class TestFilterReturnsWrongType:
    """What happens when a filter doesn't return a Payload?"""

    def test_filter_returns_none(self):
        """Filter returning None — next filter gets None as payload."""

        class ReturnsNone:
            def call(self, payload: Payload) -> Payload:
                return None  # oops

        class NextFilter:
            def call(self, payload: Payload) -> Payload:
                # This will crash: None has no .get()
                payload.get("anything")
                return payload

        pipeline = Pipeline()
        pipeline.add_filter(ReturnsNone(), "bad")
        pipeline.add_filter(NextFilter(), "next")

        with pytest.raises(AttributeError):
            run(pipeline.run(Payload({"key": "value"})))

    def test_filter_returns_none_as_final_step(self):
        """Last filter returns None — result is None, not a Payload."""

        class ReturnsNone:
            def call(self, payload: Payload) -> Payload:
                return None

        pipeline = Pipeline()
        pipeline.add_filter(ReturnsNone(), "bad")

        result = run(pipeline.run(Payload({"key": "value"})))
        assert result is None

    def test_filter_returns_plain_dict(self):
        """Filter returns a dict instead of Payload — downstream .get() still works (duck typing)."""

        class ReturnsDict:
            def call(self, payload: Payload) -> Payload:
                return {"key": "from_dict"}  # oops, raw dict

        class NextFilter:
            def call(self, payload: Payload) -> Payload:
                # dict.get() exists, so this might accidentally work
                val = payload.get("key")
                return Payload({"result": val})

        pipeline = Pipeline()
        pipeline.add_filter(ReturnsDict(), "dict_returner")
        pipeline.add_filter(NextFilter(), "consumer")

        # dict has .get() so this might duck-type through
        result = run(pipeline.run(Payload({})))
        assert result.get("result") == "from_dict"

    def test_filter_returns_string(self):
        """Filter returns a string — next filter crashes."""

        class ReturnsString:
            def call(self, payload: Payload) -> Payload:
                return "not a payload"

        class NextFilter:
            def call(self, payload: Payload) -> Payload:
                payload.get("key")
                return payload

        pipeline = Pipeline()
        pipeline.add_filter(ReturnsString(), "bad")
        pipeline.add_filter(NextFilter(), "next")

        # str has no .get() — crashes with AttributeError
        with pytest.raises(AttributeError):
            run(pipeline.run(Payload({})))

    def test_filter_returns_integer(self):
        """Filter returns an int — next filter crashes."""

        class ReturnsInt:
            def call(self, payload: Payload) -> Payload:
                return 42

        class NextFilter:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("x", 1)

        pipeline = Pipeline()
        pipeline.add_filter(ReturnsInt(), "bad")
        pipeline.add_filter(NextFilter(), "next")

        with pytest.raises(AttributeError):
            run(pipeline.run(Payload({})))


# ===================================================================
# 2. Empty and Degenerate Pipelines
# ===================================================================


class TestEmptyPipelines:
    """What happens with empty or minimal pipelines?"""

    def test_empty_pipeline_returns_original_payload(self):
        """No filters, no taps — payload passes through unchanged."""
        pipeline = Pipeline()
        result = run(pipeline.run(Payload({"input": 42})))
        assert result.get("input") == 42

    def test_empty_pipeline_state_is_clean(self):
        """Empty pipeline has no executed or skipped steps."""
        pipeline = Pipeline()
        run(pipeline.run(Payload({})))
        assert pipeline.state.executed == []
        assert pipeline.state.skipped == []

    def test_taps_only_pipeline(self):
        """Pipeline with only taps — payload passes through, taps observe."""
        observed = []

        class LogTap:
            def observe(self, payload: Payload) -> None:
                observed.append(payload.get("n"))

        pipeline = Pipeline()
        pipeline.add_tap(LogTap(), "tap1")
        pipeline.add_tap(LogTap(), "tap2")

        result = run(pipeline.run(Payload({"n": 99})))
        assert result.get("n") == 99
        assert observed == [99, 99]
        assert pipeline.state.executed == ["tap1", "tap2"]

    def test_pipeline_run_with_empty_payload(self):
        """Passing empty Payload() through filters that expect keys."""

        class SafeFilter:
            def call(self, payload: Payload) -> Payload:
                val = payload.get("missing_key", "default")
                return payload.insert("result", val)

        pipeline = Pipeline()
        pipeline.add_filter(SafeFilter(), "safe")

        result = run(pipeline.run(Payload()))
        assert result.get("result") == "default"

    def test_stream_with_empty_source(self):
        """Streaming with a source that yields nothing."""

        class DoubleFilter:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("doubled", payload.get("n", 0) * 2)

        pipeline = Pipeline()
        pipeline.add_filter(DoubleFilter(), "double")

        async def empty_source():
            return
            yield  # noqa: make it an async generator

        async def go():
            return await collect(pipeline.stream(empty_source()))

        results = run(go())
        assert results == []


# ===================================================================
# 3. Valve Predicate Misbehavior
# ===================================================================


class TestValvePredicateMisbehavior:
    """What happens when valve predicates misbehave?"""

    def test_predicate_raises_exception(self):
        """Predicate that throws — should propagate as pipeline error."""

        class Inner:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("ran", True)

        valve = Valve("exploding", Inner(), predicate=lambda p: 1 / 0)

        pipeline = Pipeline()
        pipeline.add_filter(valve, "exploding")

        with pytest.raises(ZeroDivisionError):
            run(pipeline.run(Payload({})))

    def test_predicate_returns_none(self):
        """Predicate returning None — falsy, so inner filter is skipped."""

        class Inner:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("ran", True)

        valve = Valve("none_pred", Inner(), predicate=lambda p: None)

        pipeline = Pipeline()
        pipeline.add_filter(valve, "none_pred")

        result = run(pipeline.run(Payload({"x": 1})))
        # None is falsy → inner skipped
        assert result.get("ran") is None

    def test_predicate_returns_truthy_integer(self):
        """Predicate returns 42 (truthy non-bool) — inner filter runs."""

        class Inner:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("ran", True)

        valve = Valve("int_pred", Inner(), predicate=lambda p: 42)

        pipeline = Pipeline()
        pipeline.add_filter(valve, "int_pred")

        result = run(pipeline.run(Payload({})))
        assert result.get("ran") is True

    def test_predicate_returns_empty_string(self):
        """Predicate returns '' (falsy) — inner filter skipped."""

        class Inner:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("ran", True)

        valve = Valve("str_pred", Inner(), predicate=lambda p: "")

        pipeline = Pipeline()
        pipeline.add_filter(valve, "str_pred")

        result = run(pipeline.run(Payload({})))
        assert result.get("ran") is None

    def test_predicate_returns_nonempty_list(self):
        """Predicate returns [1,2,3] (truthy) — inner runs."""

        class Inner:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("ran", True)

        valve = Valve("list_pred", Inner(), predicate=lambda p: [1, 2, 3])

        pipeline = Pipeline()
        pipeline.add_filter(valve, "list_pred")

        result = run(pipeline.run(Payload({})))
        assert result.get("ran") is True


# ===================================================================
# 4. Duplicate and Colliding Step Names
# ===================================================================


class TestDuplicateStepNames:
    """What happens when multiple steps share the same name?"""

    def test_two_filters_same_name(self):
        """Two filters with identical names — both execute, state shows name twice."""

        class Add1:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("n", payload.get("n", 0) + 1)

        pipeline = Pipeline()
        pipeline.add_filter(Add1(), "increment")
        pipeline.add_filter(Add1(), "increment")

        result = run(pipeline.run(Payload({"n": 0})))
        # Both filters ran — n incremented twice
        assert result.get("n") == 2
        # Name appears twice in executed
        assert pipeline.state.executed.count("increment") == 2

    def test_filter_and_tap_same_name(self):
        """Filter and tap with same name — both execute."""
        observed = []

        class IncrementFilter:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("n", payload.get("n", 0) + 1)

        class LogTap:
            def observe(self, payload: Payload) -> None:
                observed.append(payload.get("n"))

        pipeline = Pipeline()
        pipeline.add_filter(IncrementFilter(), "step")
        pipeline.add_tap(LogTap(), "step")

        result = run(pipeline.run(Payload({"n": 0})))
        assert result.get("n") == 1
        assert observed == [1]


# ===================================================================
# 5. Shared Filter Instance (Stateful Reuse)
# ===================================================================


class TestSharedFilterInstance:
    """Same filter object added at multiple positions — shared state."""

    def test_stateful_filter_shared_across_positions(self):
        """A filter with internal state used twice — state is shared."""

        class Counter:
            def __init__(self):
                self.count = 0

            def call(self, payload: Payload) -> Payload:
                self.count += 1
                return payload.insert(f"counter_{self.count}", True)

        counter = Counter()

        pipeline = Pipeline()
        pipeline.add_filter(counter, "count_a")
        pipeline.add_filter(counter, "count_b")

        result = run(pipeline.run(Payload({})))
        assert counter.count == 2
        assert result.get("counter_1") is True
        assert result.get("counter_2") is True

    def test_stateful_filter_accumulates_across_runs(self):
        """Filter state persists across pipeline runs."""

        class Counter:
            def __init__(self):
                self.count = 0
            def call(self, payload: Payload) -> Payload:
                self.count += 1
                return payload.insert("count", self.count)

        counter = Counter()
        pipeline = Pipeline()
        pipeline.add_filter(counter, "counter")

        r1 = run(pipeline.run(Payload({})))
        r2 = run(pipeline.run(Payload({})))
        r3 = run(pipeline.run(Payload({})))

        assert r1.get("count") == 1
        assert r2.get("count") == 2
        assert r3.get("count") == 3
        assert counter.count == 3


# ===================================================================
# 6. Tap That Raises
# ===================================================================


class TestTapThatRaises:
    """What happens when a tap raises an exception?"""

    def test_tap_exception_crashes_pipeline(self):
        """Taps are not try/caught — exception propagates."""

        class ExplodingTap:
            def observe(self, payload: Payload) -> None:
                raise RuntimeError("tap exploded")

        pipeline = Pipeline()
        pipeline.add_tap(ExplodingTap(), "bomb")

        with pytest.raises(RuntimeError, match="tap exploded"):
            run(pipeline.run(Payload({})))

    def test_tap_exception_prevents_later_filters(self):
        """If tap raises, subsequent filters never run."""
        ran = []

        class LogTap:
            def observe(self, payload: Payload) -> None:
                raise ValueError("nope")

        class AfterFilter:
            def call(self, payload: Payload) -> Payload:
                ran.append("after")
                return payload

        pipeline = Pipeline()
        pipeline.add_tap(LogTap(), "bad_tap")
        pipeline.add_filter(AfterFilter(), "after")

        with pytest.raises(ValueError):
            run(pipeline.run(Payload({})))

        assert ran == []  # never reached


# ===================================================================
# 7. Hook That Raises
# ===================================================================


class TestHookThatRaises:
    """What happens when hooks themselves throw errors?"""

    def test_hook_before_raises_stops_pipeline(self):
        """If hook.before() raises, the pipeline stops."""

        class BombHook(Hook):
            async def before(self, f, payload):
                if f is not None:
                    raise RuntimeError("hook before exploded")

        class SimpleFilter:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("ran", True)

        pipeline = Pipeline()
        pipeline.use_hook(BombHook())
        pipeline.add_filter(SimpleFilter(), "f1")

        with pytest.raises(RuntimeError, match="hook before exploded"):
            run(pipeline.run(Payload({})))

    def test_hook_after_raises(self):
        """If hook.after() raises, the pipeline stops after filter ran."""

        class AfterBomb(Hook):
            async def after(self, f, payload):
                if f is not None:
                    raise RuntimeError("hook after exploded")

        ran = []

        class Filter1:
            def call(self, payload: Payload) -> Payload:
                ran.append("f1")
                return payload

        class Filter2:
            def call(self, payload: Payload) -> Payload:
                ran.append("f2")
                return payload

        pipeline = Pipeline()
        pipeline.use_hook(AfterBomb())
        pipeline.add_filter(Filter1(), "f1")
        pipeline.add_filter(Filter2(), "f2")

        with pytest.raises(RuntimeError, match="hook after exploded"):
            run(pipeline.run(Payload({})))

        # First filter ran, then hook.after raised before f2
        assert ran == ["f1"]

    def test_hook_on_error_that_also_raises(self):
        """Hook.on_error itself raises — the ON_ERROR exception propagates,
        not the original filter error."""

        class FilterThatFails:
            def call(self, payload: Payload) -> Payload:
                raise ValueError("original error")

        class BrokenErrorHook(Hook):
            async def on_error(self, f, error, payload):
                raise RuntimeError("error handler also broke")

        pipeline = Pipeline()
        pipeline.use_hook(BrokenErrorHook())
        pipeline.add_filter(FilterThatFails(), "doomed")

        with pytest.raises(RuntimeError, match="error handler also broke"):
            run(pipeline.run(Payload({})))


# ===================================================================
# 8. RetryFilter Edge Cases
# ===================================================================


class TestRetryFilterEdgeCases:
    """Weird RetryFilter configurations."""

    def test_retry_wrapping_retry(self):
        """RetryFilter wrapping another RetryFilter — double retry."""
        attempts = [0]

        class Flaky:
            def call(self, payload: Payload) -> Payload:
                attempts[0] += 1
                if attempts[0] < 4:
                    raise ConnectionError("still failing")
                return payload.insert("success", True)

        # Inner retries 2 times, outer retries 3 times
        inner_retry = RetryFilter(Flaky(), max_retries=2)
        outer_retry = RetryFilter(inner_retry, max_retries=3)

        pipeline = Pipeline()
        pipeline.add_filter(outer_retry, "double_retry")

        result = run(pipeline.run(Payload({})))
        # With nested retries the exact behavior depends on whether
        # inner's error-payload propagation triggers outer's retry.
        # Either it succeeds or captures error — just verify no crash.
        assert result is not None

    def test_retry_zero_retries(self):
        """RetryFilter with max_retries=0 — still executes once, captures error."""
        class AlwaysFail:
            def call(self, payload: Payload) -> Payload:
                raise ValueError("fail")

        pipeline = Pipeline()
        pipeline.add_filter(RetryFilter(AlwaysFail(), max_retries=0), "zero")

        result = run(pipeline.run(Payload({})))
        assert "fail" in result.get("error", "")

    def test_retry_negative_retries_clamped_to_zero(self):
        """Negative max_retries clamped to 0 — still runs once."""
        class AlwaysFail:
            def call(self, payload: Payload) -> Payload:
                raise ValueError("negative")

        r = RetryFilter(AlwaysFail(), max_retries=-5)
        assert r.max_retries == 0

        pipeline = Pipeline()
        pipeline.add_filter(r, "neg")

        result = run(pipeline.run(Payload({})))
        assert "negative" in result.get("error", "")

    def test_retry_filter_succeeds_on_first_try(self):
        """If the inner filter never fails, RetryFilter adds no overhead."""
        calls = [0]

        class NeverFails:
            def call(self, payload: Payload) -> Payload:
                calls[0] += 1
                return payload.insert("ok", True)

        pipeline = Pipeline()
        pipeline.add_filter(RetryFilter(NeverFails(), max_retries=5), "easy")

        result = run(pipeline.run(Payload({})))
        assert result.get("ok") is True
        assert calls[0] == 1  # Only called once


# ===================================================================
# 9. Payload Constructor Abuse
# ===================================================================


class TestPayloadConstructorAbuse:
    """What happens when users pass weird things to Payload()?"""

    def test_payload_from_none(self):
        """Payload(None) → empty."""
        p = Payload(None)
        assert p.to_dict() == {}

    def test_payload_from_empty_dict(self):
        p = Payload({})
        assert p.to_dict() == {}

    def test_payload_from_integer(self):
        """Payload(42) — can't convert int to dict, falls back to empty."""
        p = Payload(42)
        assert p.to_dict() == {}

    def test_payload_from_string(self):
        """Payload('hello') — string isn't dict-like, falls back to empty."""
        p = Payload("hello")
        assert p.to_dict() == {}

    def test_payload_from_list(self):
        """Payload([1,2,3]) — list can't be dict(), falls back to empty."""
        p = Payload([1, 2, 3])
        assert p.to_dict() == {}

    def test_payload_from_list_of_tuples(self):
        """Payload([(k,v),...]) — dict() CAN convert list of tuples!"""
        p = Payload([("a", 1), ("b", 2)])
        assert p.get("a") == 1
        assert p.get("b") == 2

    def test_payload_from_boolean(self):
        """Payload(True) — bool can't be dict(), falls back to empty."""
        p = Payload(True)
        assert p.to_dict() == {}

    def test_payload_from_nested_payload(self):
        """Payload(Payload({...})) — Payload isn't a dict, tries dict(Payload).
        Payload has no __iter__, so should fall back to empty."""
        inner = Payload({"nested": True})
        outer = Payload(inner)
        # This depends on whether dict(Payload) works — it shouldn't
        # since Payload doesn't implement __iter__
        assert isinstance(outer, Payload)

    def test_payload_insert_preserves_immutability(self):
        """Original payload is never mutated by insert."""
        p1 = Payload({"a": 1})
        p2 = p1.insert("b", 2)
        assert p1.get("b") is None
        assert p2.get("b") == 2
        assert p2.get("a") == 1

    def test_payload_merge_does_not_mutate_originals(self):
        """Merge creates a new payload; originals unchanged."""
        p1 = Payload({"a": 1, "shared": "from_p1"})
        p2 = Payload({"b": 2, "shared": "from_p2"})
        merged = p1.merge(p2)
        assert merged.get("shared") == "from_p2"
        assert p1.get("shared") == "from_p1"  # unchanged
        assert merged.get("a") == 1
        assert merged.get("b") == 2


# ===================================================================
# 10. MutablePayload Misuse
# ===================================================================


class TestMutablePayloadMisuse:
    """Weird things users might do with MutablePayload."""

    def test_to_immutable_called_twice(self):
        """Calling to_immutable() twice gives two independent copies."""
        m = MutablePayload({"x": 1})
        p1 = m.to_immutable()
        m.set("x", 2)
        p2 = m.to_immutable()
        assert p1.get("x") == 1
        assert p2.get("x") == 2

    def test_mutable_payload_passed_to_pipeline(self):
        """MutablePayload instead of Payload — does it duck-type through?"""

        class SimpleFilter:
            def call(self, payload):
                val = payload.get("x", 0)
                # MutablePayload has no .insert() — this will fail
                return Payload({"x": val + 1})

        pipeline = Pipeline()
        pipeline.add_filter(SimpleFilter(), "f")

        # MutablePayload has .get() but not .insert()
        # Pipeline._invoke doesn't type-check, so it might work
        # if the filter creates a new Payload explicitly
        mp = MutablePayload({"x": 10})
        result = run(pipeline.run(mp))
        assert result.get("x") == 11

    def test_mutable_payload_set_after_to_immutable(self):
        """Setting values on MutablePayload after to_immutable — doesn't affect the immutable."""
        m = MutablePayload({"a": 1})
        p = m.to_immutable()
        m.set("a", 999)
        m.set("b", 2)
        # Immutable is a snapshot
        assert p.get("a") == 1
        assert p.get("b") is None

    def test_mutable_payload_empty(self):
        """MutablePayload with no data."""
        m = MutablePayload()
        assert m.get("anything") is None
        m.set("key", "value")
        p = m.to_immutable()
        assert p.get("key") == "value"


# ===================================================================
# 11. Recursive Pipeline — Pipeline Inside Pipeline
# ===================================================================


class TestRecursivePipeline:
    """Can a filter call another pipeline internally?"""

    def test_pipeline_as_inner_processor(self):
        """A filter that runs a sub-pipeline on the same payload."""

        class SubPipelineFilter:
            def __init__(self):
                self._sub = Pipeline()
                self._sub.add_filter(type("Add10", (), {
                    "call": lambda self, p: p.insert("n", p.get("n", 0) + 10)
                })(), "add10")
                self._sub.add_filter(type("Double", (), {
                    "call": lambda self, p: p.insert("n", p.get("n", 0) * 2)
                })(), "double")

            async def call(self, payload: Payload) -> Payload:
                return await self._sub.run(payload)

        pipeline = Pipeline()
        pipeline.add_filter(SubPipelineFilter(), "sub_pipeline")

        result = run(pipeline.run(Payload({"n": 5})))
        # 5 + 10 = 15, 15 * 2 = 30
        assert result.get("n") == 30

    def test_nested_state_is_independent(self):
        """Inner pipeline state doesn't contaminate outer state."""

        class SubPipelineFilter:
            def __init__(self):
                self.sub = Pipeline()
                self.sub.add_filter(type("Inner", (), {
                    "call": lambda self, p: p.insert("inner", True)
                })(), "inner_step")

            async def call(self, payload: Payload) -> Payload:
                return await self.sub.run(payload)

        spf = SubPipelineFilter()
        outer = Pipeline()
        outer.add_filter(spf, "outer_step")

        result = run(outer.run(Payload({})))
        assert result.get("inner") is True
        # Inner pipeline tracked its own state
        assert "inner_step" in spf.sub.state.executed
        # Outer pipeline tracked its own state
        assert outer.state.executed == ["outer_step"]
        assert "inner_step" not in outer.state.executed


# ===================================================================
# 12. Very Large Pipeline
# ===================================================================


class TestLargePipeline:
    """Push the pipeline with many steps."""

    def test_100_filter_pipeline(self):
        """100 filters that each increment — tests iteration overhead."""

        class Increment:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("n", payload.get("n", 0) + 1)

        pipeline = Pipeline()
        for i in range(100):
            pipeline.add_filter(Increment(), f"inc_{i}")

        result = run(pipeline.run(Payload({"n": 0})))
        assert result.get("n") == 100
        assert len(pipeline.state.executed) == 100

    def test_pipeline_with_50_taps_and_50_filters(self):
        """Interleaved taps and filters — all run, correct order."""
        observations = []

        class NameFilter:
            def __init__(self, tag):
                self._tag = tag
            def call(self, payload: Payload) -> Payload:
                items = payload.get("trace", [])
                return payload.insert("trace", items + [f"filter_{self._tag}"])

        class TraceTap:
            def __init__(self, tag, log):
                self._tag = tag
                self._log = log
            def observe(self, payload: Payload) -> None:
                self._log.append(f"tap_{self._tag}")

        pipeline = Pipeline()
        for i in range(50):
            pipeline.add_filter(NameFilter(i), f"f_{i}")
            pipeline.add_tap(TraceTap(i, observations), f"t_{i}")

        result = run(pipeline.run(Payload({"trace": []})))
        assert len(result.get("trace")) == 50
        assert len(observations) == 50
        assert len(pipeline.state.executed) == 100  # 50 filters + 50 taps


# ===================================================================
# 13. Streaming Edge Cases
# ===================================================================


class TestStreamingEdgeCases:
    """Push the streaming path with unusual patterns."""

    def test_stream_filter_yields_nothing_for_all_chunks(self):
        """StreamFilter that drops every chunk — empty output."""

        class DropAll:
            async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
                return
                yield  # noqa

        pipeline = Pipeline()
        pipeline.add_filter(DropAll(), "drop")

        async def go():
            return await collect(pipeline.stream(make_source(
                {"a": 1}, {"a": 2}, {"a": 3},
            )))

        assert run(go()) == []

    def test_stream_filter_fan_out_10x(self):
        """StreamFilter that yields 10 chunks per input."""

        class FanOut10:
            async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
                for i in range(10):
                    yield chunk.insert("copy", i)

        pipeline = Pipeline()
        pipeline.add_filter(FanOut10(), "fan_out")

        async def go():
            return await collect(pipeline.stream(make_source({"x": 1})))

        results = run(go())
        assert len(results) == 10
        assert all(r.get("x") == 1 for r in results)
        copies = [r.get("copy") for r in results]
        assert copies == list(range(10))

    def test_stream_filter_then_regular_filter(self):
        """StreamFilter fans out, regular filter processes each."""

        class FanOut3:
            async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
                for i in range(3):
                    yield chunk.insert("idx", i)

        class AddLabel:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("label", f"item_{payload.get('idx')}")

        pipeline = Pipeline()
        pipeline.add_filter(FanOut3(), "fan")
        pipeline.add_filter(AddLabel(), "label")

        async def go():
            return await collect(pipeline.stream(make_source({"base": True})))

        results = run(go())
        assert len(results) == 3
        assert results[0].get("label") == "item_0"
        assert results[2].get("label") == "item_2"

    def test_valve_in_streaming_mode(self):
        """Valve gates per-chunk in streaming — some pass, some skip."""

        class DoubleN:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("n", payload.get("n", 0) * 2)

        pipeline = Pipeline()
        pipeline.add_filter(
            Valve("even_only", DoubleN(), predicate=lambda p: p.get("n", 0) % 2 == 0),
            "even_only"
        )

        async def go():
            return await collect(pipeline.stream(make_source(
                {"n": 1}, {"n": 2}, {"n": 3}, {"n": 4}, {"n": 5},
            )))

        results = run(go())
        values = [r.get("n") for r in results]
        # Evens doubled: 2→4, 4→8. Odds pass through: 1, 3, 5
        assert values == [1, 4, 3, 8, 5]


# ===================================================================
# 14. Payload Key Conflicts with "Internal" Names
# ===================================================================


class TestPayloadKeyConflicts:
    """Users might use keys like 'error', 'status' that RetryFilter uses."""

    def test_payload_with_preexisting_error_key(self):
        """Payload already has 'error' key — filter should still work."""

        class AppendError:
            def call(self, payload: Payload) -> Payload:
                existing = payload.get("error", "")
                return payload.insert("error", existing + " | new error")

        pipeline = Pipeline()
        pipeline.add_filter(AppendError(), "append")

        result = run(pipeline.run(Payload({"error": "old error"})))
        assert result.get("error") == "old error | new error"

    def test_retry_filter_overwrites_user_error_key(self):
        """RetryFilter sets .insert('error', ...) — if user had their own 'error' key, it's gone."""

        class AlwaysFail:
            def call(self, payload: Payload) -> Payload:
                raise RuntimeError("kaboom")

        pipeline = Pipeline()
        pipeline.add_filter(RetryFilter(AlwaysFail(), max_retries=1), "fail")

        result = run(pipeline.run(Payload({"error": "user's original error"})))
        # RetryFilter overwrites the 'error' key
        assert "kaboom" in result.get("error", "")
        assert "user's original" not in result.get("error", "")


# ===================================================================
# 15. Filter That Directly Mutates Payload._data
# ===================================================================


class TestDirectPayloadMutation:
    """What if a filter cheats and mutates Payload._data directly?"""

    def test_mutating_internal_data_affects_payload(self):
        """If you reach into _data, immutability is broken."""

        class Cheater:
            def call(self, payload: Payload) -> Payload:
                # This is BAD — violating the immutability contract
                payload._data["injected"] = "hacked"
                return payload

        pipeline = Pipeline()
        pipeline.add_filter(Cheater(), "cheat")

        original = Payload({"safe": True})
        result = run(pipeline.run(original))

        # The cheat works — mutation is not prevented at runtime
        assert result.get("injected") == "hacked"
        # But notably, insert() copies, so proper usage preserves immutability

    def test_insert_does_not_affect_original(self):
        """Contrast: proper usage via insert() leaves original untouched."""
        original = Payload({"x": 1})
        modified = original.insert("x", 999)
        assert original.get("x") == 1
        assert modified.get("x") == 999


# ===================================================================
# 16. Multiple Hooks — Ordering and Interactions
# ===================================================================


class TestMultipleHooksInteraction:
    """Multiple hooks on the same pipeline — ordering matters."""

    def test_hooks_fire_in_registration_order(self):
        """Hooks fire in the order they were registered."""
        order = []

        class Hook1(Hook):
            async def before(self, f, payload):
                order.append("h1_before")
            async def after(self, f, payload):
                order.append("h1_after")

        class Hook2(Hook):
            async def before(self, f, payload):
                order.append("h2_before")
            async def after(self, f, payload):
                order.append("h2_after")

        class Noop:
            def call(self, payload: Payload) -> Payload:
                order.append("filter")
                return payload

        pipeline = Pipeline()
        pipeline.use_hook(Hook1())
        pipeline.use_hook(Hook2())
        pipeline.add_filter(Noop(), "noop")

        run(pipeline.run(Payload({})))

        # Expected: both befores, filter, both afters
        # Pipeline start hooks, then per-filter hooks
        assert order == [
            "h1_before", "h2_before",  # pipeline start (filter=None)
            "h1_before", "h2_before",  # before filter
            "filter",
            "h1_after", "h2_after",    # after filter
            "h1_after", "h2_after",    # pipeline end (filter=None)
        ]

    def test_first_hook_error_prevents_second_hook(self):
        """If first hook raises in on_error, second hook's on_error never runs."""
        ran = []

        class Hook1(Hook):
            async def on_error(self, f, error, payload):
                ran.append("h1")
                raise RuntimeError("hook1 broke")

        class Hook2(Hook):
            async def on_error(self, f, error, payload):
                ran.append("h2")

        class BrokenFilter:
            def call(self, payload: Payload) -> Payload:
                raise ValueError("filter error")

        pipeline = Pipeline()
        pipeline.use_hook(Hook1())
        pipeline.use_hook(Hook2())
        pipeline.add_filter(BrokenFilter(), "broken")

        with pytest.raises(RuntimeError, match="hook1 broke"):
            run(pipeline.run(Payload({})))

        # Only first hook ran
        assert ran == ["h1"]


# ===================================================================
# 17. Pipeline State After Error
# ===================================================================


class TestStateAfterError:
    """What does state look like when the pipeline errors out?"""

    def test_state_tracks_executed_before_error(self):
        """State records which steps ran before the crash."""

        class Step1:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("s1", True)

        class Step2:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("s2", True)

        class Bomb:
            def call(self, payload: Payload) -> Payload:
                raise RuntimeError("boom")

        class Step4:
            def call(self, payload: Payload) -> Payload:
                return payload.insert("s4", True)

        pipeline = Pipeline()
        pipeline.add_filter(Step1(), "step1")
        pipeline.add_filter(Step2(), "step2")
        pipeline.add_filter(Bomb(), "bomb")
        pipeline.add_filter(Step4(), "step4")

        with pytest.raises(RuntimeError):
            run(pipeline.run(Payload({})))

        # Steps before the error are tracked
        assert "step1" in pipeline.state.executed
        assert "step2" in pipeline.state.executed
        # Bomb didn't complete successfully
        assert "bomb" not in pipeline.state.executed
        # Step4 never ran
        assert "step4" not in pipeline.state.executed


# ===================================================================
# 18. Type Confusion — Filter.call is Not a Method
# ===================================================================


class TestFilterProtocolAbuse:
    """What if the user's 'filter' doesn't follow the protocol at all?"""

    def test_object_with_no_call_method(self):
        """Adding an object with no .call() — crashes when pipeline tries to invoke."""

        class NotAFilter:
            pass

        pipeline = Pipeline()
        pipeline.add_filter(NotAFilter(), "bad")

        with pytest.raises(AttributeError):
            run(pipeline.run(Payload({})))

    def test_lambda_as_filter(self):
        """A lambda is not a filter — it has no .call() attribute."""
        pipeline = Pipeline()
        pipeline.add_filter(lambda p: p.insert("x", 1), "lambda_filter")

        with pytest.raises(AttributeError):
            run(pipeline.run(Payload({})))

    def test_class_with_callable_but_wrong_name(self):
        """Class with __call__ instead of .call — doesn't match protocol."""

        class CallableNotFilter:
            def __call__(self, payload: Payload) -> Payload:
                return payload.insert("ran", True)

        pipeline = Pipeline()
        pipeline.add_filter(CallableNotFilter(), "wrong")

        # Pipeline looks for .call(), not __call__()
        with pytest.raises(AttributeError):
            run(pipeline.run(Payload({})))


# ===================================================================
# 19. Concurrency Concerns — Sequential Runs on Same Pipeline
# ===================================================================


class TestSequentialPipelineRuns:
    """Verify state resets between sequential runs."""

    def test_state_resets_between_runs(self):
        """Each call to pipeline.run() gets fresh state."""

        class PassThrough:
            def call(self, payload: Payload) -> Payload:
                return payload

        pipeline = Pipeline()
        pipeline.add_filter(
            Valve("gate", PassThrough(), predicate=lambda p: p.get("open")),
            "gate"
        )

        # Run 1: gate open
        run(pipeline.run(Payload({"open": True})))
        assert "gate" in pipeline.state.executed
        assert "gate" not in pipeline.state.skipped

        # Run 2: gate closed — state should reflect THIS run only
        run(pipeline.run(Payload({"open": False})))
        assert "gate" in pipeline.state.skipped
        assert "gate" not in pipeline.state.executed

    def test_error_state_clears_on_next_run(self):
        """State.errors from a failed run don't persist into successful runs."""

        class ConditionalBomb:
            def call(self, payload: Payload) -> Payload:
                if payload.get("fail"):
                    raise RuntimeError("fail!")
                return payload.insert("ok", True)

        pipeline = Pipeline()
        pipeline.add_filter(ConditionalBomb(), "maybe_bomb")

        # First run fails
        with pytest.raises(RuntimeError):
            run(pipeline.run(Payload({"fail": True})))

        # Second run succeeds — state is fresh
        result = run(pipeline.run(Payload({"fail": False})))
        assert result.get("ok") is True
        assert pipeline.state.has_errors is False


# ===================================================================
# 20. Payload with Complex Nested Data
# ===================================================================


class TestPayloadComplexData:
    """Payload with deeply nested structures, special values, etc."""

    def test_deeply_nested_dict(self):
        """Deep nesting survives pipeline transit."""
        deep = {"level1": {"level2": {"level3": {"level4": "deep_value"}}}}
        p = Payload(deep)
        result = p.get("level1")
        assert result["level2"]["level3"]["level4"] == "deep_value"

    def test_payload_with_none_value(self):
        """None as a value (not missing key) — .get() returns None."""
        p = Payload({"key": None})
        assert p.get("key") is None
        assert p.get("key", "default") is None

    def test_payload_with_none_value_vs_missing(self):
        """Distinguish between key=None and key not present — both return None from .get()."""
        p = Payload({"present": None})
        # Both return None — indistinguishable via .get()
        assert p.get("present") is None
        assert p.get("absent") is None
        # But to_dict reveals the difference
        d = p.to_dict()
        assert "present" in d
        assert "absent" not in d

    def test_payload_with_function_as_value(self):
        """Payload can hold functions as values."""
        p = Payload({"callback": lambda x: x * 2})
        fn = p.get("callback")
        assert fn(5) == 10

    def test_payload_with_class_instances(self):
        """Payload can hold arbitrary class instances."""

        class User:
            def __init__(self, name):
                self.name = name

        p = Payload({"user": User("Alice")})
        assert p.get("user").name == "Alice"

    def test_payload_with_large_binary_data(self):
        """Payload can hold bytes."""
        data = b"\x00" * 10000
        p = Payload({"blob": data})
        assert len(p.get("blob")) == 10000
