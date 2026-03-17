"""Unit tests for storage.py — Iteration 2 additions.

Tests for:
  - Temporal queries (list_runs_by_time, count_runs)
  - Metric aggregation (aggregate_metric, metric_time_series, list_metric_names)
  - Tags (add_tag, get_tags, list_runs_by_tag, remove_tag)
  - Annotations (add_annotation, get_annotations)
  - Search (search_raw_events, event_type_counts)
"""

from datetime import datetime, timedelta, timezone

import pytest

from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    Metric,
    RawEvent,
    RunConfig,
    RunOutcome,
    RunRecord,
    TurnSnapshot,
    _utcnow,
)


@pytest.fixture
def store(tmp_path):
    s = EvalStore(tmp_path / "test.db")
    yield s
    s.close()


def _make_run(
    run_id: str = "r1",
    outcome: RunOutcome = RunOutcome.SUCCESS,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    scenario_id: str | None = None,
    model: str = "gpt-4.1",
    n_metrics: int = 2,
) -> RunRecord:
    now = started_at or _utcnow()
    end = ended_at or (now + timedelta(seconds=5))
    metrics = ()
    if n_metrics >= 1:
        metrics += (
            Metric(name="turns_total", value=3.0, unit="count"),
        )
    if n_metrics >= 2:
        metrics += (
            Metric(name="cost_premium_requests", value=1.5, unit="requests"),
        )
    return RunRecord(
        run_id=run_id,
        config=RunConfig(model=model),
        outcome=outcome,
        started_at=now,
        ended_at=end,
        scenario_id=scenario_id,
        metrics=metrics,
    )


# ── Temporal Queries ──────────────────────────────────────────────────


@pytest.mark.unit
class TestListRunsByTime:
    def test_all_runs(self, store):
        store.save_run(_make_run("r1"))
        store.save_run(_make_run("r2"))
        runs = store.list_runs_by_time()
        assert len(runs) == 2

    def test_after_filter(self, store):
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        future = datetime(2030, 1, 1, tzinfo=timezone.utc)
        store.save_run(_make_run("old", started_at=past))
        store.save_run(_make_run("new", started_at=future))
        runs = store.list_runs_by_time(
            after=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        assert len(runs) == 1
        assert runs[0].run_id == "new"

    def test_before_filter(self, store):
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        future = datetime(2030, 1, 1, tzinfo=timezone.utc)
        store.save_run(_make_run("old", started_at=past))
        store.save_run(_make_run("new", started_at=future))
        runs = store.list_runs_by_time(
            before=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        assert len(runs) == 1
        assert runs[0].run_id == "old"

    def test_outcome_filter(self, store):
        store.save_run(_make_run("ok", outcome=RunOutcome.SUCCESS))
        store.save_run(_make_run("bad", outcome=RunOutcome.FAILURE))
        runs = store.list_runs_by_time(outcome=RunOutcome.SUCCESS)
        assert len(runs) == 1
        assert runs[0].run_id == "ok"


@pytest.mark.unit
class TestCountRuns:
    def test_basic(self, store):
        store.save_run(_make_run("r1"))
        store.save_run(_make_run("r2"))
        assert store.count_runs() == 2

    def test_with_outcome(self, store):
        store.save_run(_make_run("ok", outcome=RunOutcome.SUCCESS))
        store.save_run(_make_run("bad", outcome=RunOutcome.FAILURE))
        assert store.count_runs(outcome=RunOutcome.SUCCESS) == 1

    def test_with_scenario(self, store):
        store.save_run(_make_run("r1", scenario_id="s1"))
        store.save_run(_make_run("r2", scenario_id="s2"))
        assert store.count_runs(scenario_id="s1") == 1


# ── Metric Aggregation ───────────────────────────────────────────────


@pytest.mark.unit
class TestAggregateMetric:
    def test_basic(self, store):
        store.save_run(_make_run("r1"))
        store.save_run(_make_run("r2"))
        agg = store.aggregate_metric("turns_total")
        assert agg["count"] == 2
        assert agg["avg"] == pytest.approx(3.0)
        assert agg["min"] == pytest.approx(3.0)
        assert agg["max"] == pytest.approx(3.0)
        assert agg["sum"] == pytest.approx(6.0)

    def test_no_matches(self, store):
        agg = store.aggregate_metric("nonexistent")
        assert agg["count"] == 0

    def test_with_scenario_filter(self, store):
        store.save_run(_make_run("r1", scenario_id="s1"))
        store.save_run(_make_run("r2", scenario_id="s2"))
        agg = store.aggregate_metric("turns_total", scenario_id="s1")
        assert agg["count"] == 1


@pytest.mark.unit
class TestMetricTimeSeries:
    def test_ordered_by_time(self, store):
        t1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2025, 1, 2, tzinfo=timezone.utc)
        store.save_run(_make_run("r1", started_at=t1))
        store.save_run(_make_run("r2", started_at=t2))
        series = store.metric_time_series("turns_total")
        assert len(series) == 2
        # Should be ordered by time
        assert series[0][0] <= series[1][0]

    def test_returns_tuples(self, store):
        store.save_run(_make_run("r1"))
        series = store.metric_time_series("turns_total")
        assert len(series) == 1
        ts, val = series[0]
        assert isinstance(ts, str)
        assert val == pytest.approx(3.0)


@pytest.mark.unit
class TestListMetricNames:
    def test_basic(self, store):
        store.save_run(_make_run("r1"))
        names = store.list_metric_names()
        assert "turns_total" in names
        assert "cost_premium_requests" in names

    def test_empty(self, store):
        assert store.list_metric_names() == []


# ── Tags ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTags:
    def test_add_and_get(self, store):
        store.save_run(_make_run("r1"))
        store.add_tag("r1", "version", "v2.1.0")
        tags = store.get_tags("r1")
        assert tags["version"] == "v2.1.0"

    def test_multiple_tags(self, store):
        store.save_run(_make_run("r1"))
        store.add_tag("r1", "version", "v2.1.0")
        store.add_tag("r1", "env", "staging")
        tags = store.get_tags("r1")
        assert len(tags) == 2
        assert tags["env"] == "staging"

    def test_overwrite_tag(self, store):
        store.save_run(_make_run("r1"))
        store.add_tag("r1", "version", "v1.0")
        store.add_tag("r1", "version", "v2.0")
        tags = store.get_tags("r1")
        assert tags["version"] == "v2.0"

    def test_no_tags(self, store):
        store.save_run(_make_run("r1"))
        assert store.get_tags("r1") == {}

    def test_remove_tag(self, store):
        store.save_run(_make_run("r1"))
        store.add_tag("r1", "version", "v1.0")
        store.remove_tag("r1", "version")
        assert store.get_tags("r1") == {}


@pytest.mark.unit
class TestListRunsByTag:
    def test_by_key_and_value(self, store):
        store.save_run(_make_run("r1"))
        store.save_run(_make_run("r2"))
        store.add_tag("r1", "env", "prod")
        store.add_tag("r2", "env", "dev")
        runs = store.list_runs_by_tag("env", "prod")
        assert len(runs) == 1
        assert runs[0].run_id == "r1"

    def test_by_key_only(self, store):
        store.save_run(_make_run("r1"))
        store.save_run(_make_run("r2"))
        store.add_tag("r1", "env", "prod")
        store.add_tag("r2", "env", "dev")
        runs = store.list_runs_by_tag("env")
        assert len(runs) == 2

    def test_no_matches(self, store):
        store.save_run(_make_run("r1"))
        runs = store.list_runs_by_tag("nonexistent")
        assert runs == []


# ── Annotations ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestAnnotations:
    def test_add_and_get(self, store):
        store.save_run(_make_run("r1"))
        store.add_annotation("r1", "This run looks good", author="jwink")
        annotations = store.get_annotations("r1")
        assert len(annotations) == 1
        assert annotations[0]["content"] == "This run looks good"
        assert annotations[0]["author"] == "jwink"

    def test_multiple_annotations(self, store):
        store.save_run(_make_run("r1"))
        store.add_annotation("r1", "First note")
        store.add_annotation("r1", "Second note")
        annotations = store.get_annotations("r1")
        assert len(annotations) == 2

    def test_with_metadata(self, store):
        store.save_run(_make_run("r1"))
        store.add_annotation(
            "r1", "Bug found",
            metadata={"bug_id": "BUG-123"},
        )
        annotations = store.get_annotations("r1")
        assert annotations[0]["metadata"]["bug_id"] == "BUG-123"

    def test_no_annotations(self, store):
        store.save_run(_make_run("r1"))
        assert store.get_annotations("r1") == []


# ── Search ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSearchRawEvents:
    def test_by_type(self, store):
        store.save_run(_make_run("r1"))
        store.save_raw_event(RawEvent(
            run_id="r1", event_type="audit", payload={"x": 1},
        ))
        store.save_raw_event(RawEvent(
            run_id="r1", event_type="sdk_response", payload={"y": 2},
        ))
        events = store.search_raw_events(event_type="audit")
        # May include events from save_run too
        assert all(e.event_type == "audit" for e in events)

    def test_payload_contains(self, store):
        store.save_run(_make_run("r1"))
        store.save_raw_event(RawEvent(
            run_id="r1", event_type="test",
            payload={"message": "hello world"},
        ))
        events = store.search_raw_events(payload_contains="hello")
        assert len(events) >= 1

    def test_no_matches(self, store):
        events = store.search_raw_events(payload_contains="nonexistent_xyz")
        assert events == []


@pytest.mark.unit
class TestEventTypeCounts:
    def test_basic(self, store):
        store.save_run(_make_run("r1"))
        store.save_raw_event(RawEvent(
            run_id="r1", event_type="type_a", payload={},
        ))
        store.save_raw_event(RawEvent(
            run_id="r1", event_type="type_a", payload={},
        ))
        store.save_raw_event(RawEvent(
            run_id="r1", event_type="type_b", payload={},
        ))
        counts = store.event_type_counts(run_id="r1")
        assert counts.get("type_a", 0) == 2
        assert counts.get("type_b", 0) == 1

    def test_empty(self, store):
        counts = store.event_type_counts()
        # May be empty or have default entries
        assert isinstance(counts, dict)
