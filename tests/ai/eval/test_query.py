"""Unit tests for codeupipe.ai.eval.query — fluent query builder."""

from datetime import timedelta

import pytest

from codeupipe.ai.eval.query import RunQuery
from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    Metric,
    RunConfig,
    RunOutcome,
    RunRecord,
    TurnSnapshot,
    _utcnow,
)


@pytest.fixture
def store(tmp_path):
    s = EvalStore(tmp_path / "query_test.db")
    yield s
    s.close()


def _make_run(
    run_id: str,
    *,
    model: str = "gpt-4.1",
    outcome: RunOutcome = RunOutcome.SUCCESS,
    scenario_id: str = "",
    experiment_id: str = "",
    started_at=None,
    metrics: tuple[Metric, ...] = (),
) -> RunRecord:
    now = started_at or _utcnow()
    default_metrics = (
        Metric(name="turns_total", value=3.0),
        Metric(name="tokens_total", value=300.0),
    )
    return RunRecord(
        run_id=run_id,
        config=RunConfig(model=model),
        outcome=outcome,
        scenario_id=scenario_id,
        experiment_id=experiment_id,
        started_at=now,
        ended_at=now + timedelta(seconds=5),
        turns=(
            TurnSnapshot(
                iteration=0,
                turn_type="assistant",
                input_prompt="hello",
                tokens_estimated=100,
                duration_ms=50.0,
            ),
        ),
        metrics=metrics or default_metrics,
    )


def _seed_runs(store: EvalStore) -> list[RunRecord]:
    """Seed store with 6 varied runs and return them."""
    now = _utcnow()
    runs = [
        _make_run("r1", model="gpt-4.1", outcome=RunOutcome.SUCCESS,
                   scenario_id="sc_a", started_at=now - timedelta(days=10)),
        _make_run("r2", model="gpt-4.1", outcome=RunOutcome.FAILURE,
                   scenario_id="sc_a", started_at=now - timedelta(days=8)),
        _make_run("r3", model="claude-sonnet-4", outcome=RunOutcome.SUCCESS,
                   scenario_id="sc_b", started_at=now - timedelta(days=5)),
        _make_run("r4", model="claude-sonnet-4", outcome=RunOutcome.SUCCESS,
                   scenario_id="sc_b", started_at=now - timedelta(days=3)),
        _make_run("r5", model="gpt-4.1", outcome=RunOutcome.SUCCESS,
                   scenario_id="sc_a", started_at=now - timedelta(days=1)),
        _make_run("r6", model="gpt-4.1", outcome=RunOutcome.TIMEOUT,
                   scenario_id="sc_c", started_at=now),
    ]
    for r in runs:
        store.save_run(r)
    return runs


# ── Basic queries ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestRunQueryBasic:
    def test_all_runs(self, store):
        _seed_runs(store)
        runs = RunQuery(store).execute()
        assert len(runs) == 6

    def test_filter_by_scenario(self, store):
        _seed_runs(store)
        runs = RunQuery(store).scenario("sc_a").execute()
        assert len(runs) == 3
        assert all(r.scenario_id == "sc_a" for r in runs)

    def test_filter_by_outcome(self, store):
        _seed_runs(store)
        runs = RunQuery(store).outcome(RunOutcome.SUCCESS).execute()
        assert len(runs) == 4
        assert all(str(r.outcome) == "success" for r in runs)

    def test_filter_by_model(self, store):
        _seed_runs(store)
        runs = RunQuery(store).model("claude-sonnet-4").execute()
        assert len(runs) == 2
        assert all(r.config.model == "claude-sonnet-4" for r in runs)

    def test_limit(self, store):
        _seed_runs(store)
        runs = RunQuery(store).limit(2).execute()
        assert len(runs) == 2

    def test_run_ids_filter(self, store):
        _seed_runs(store)
        runs = RunQuery(store).run_ids(["r1", "r3"]).execute()
        assert len(runs) == 2
        assert {r.run_id for r in runs} == {"r1", "r3"}


# ── Time-based queries ───────────────────────────────────────────────


@pytest.mark.unit
class TestRunQueryTime:
    def test_after(self, store):
        _seed_runs(store)
        cutoff = _utcnow() - timedelta(days=4)
        runs = RunQuery(store).after(cutoff).execute()
        assert len(runs) >= 3  # r4, r5, r6

    def test_before(self, store):
        _seed_runs(store)
        cutoff = _utcnow() - timedelta(days=6)
        runs = RunQuery(store).before(cutoff).execute()
        assert len(runs) >= 2  # r1, r2

    def test_time_range(self, store):
        _seed_runs(store)
        start = _utcnow() - timedelta(days=6)
        end = _utcnow() - timedelta(days=2)
        runs = RunQuery(store).after(start).before(end).execute()
        assert len(runs) >= 2  # r3, r4


# ── Chaining filters ─────────────────────────────────────────────────


@pytest.mark.unit
class TestRunQueryChaining:
    def test_model_and_outcome(self, store):
        _seed_runs(store)
        runs = (
            RunQuery(store)
            .model("gpt-4.1")
            .outcome(RunOutcome.SUCCESS)
            .execute()
        )
        assert len(runs) == 2  # r1, r5
        for r in runs:
            assert r.config.model == "gpt-4.1"
            assert str(r.outcome) == "success"

    def test_scenario_and_limit(self, store):
        _seed_runs(store)
        runs = RunQuery(store).scenario("sc_a").limit(2).execute()
        assert len(runs) == 2


# ── Convenience methods ──────────────────────────────────────────────


@pytest.mark.unit
class TestRunQueryConvenience:
    def test_count(self, store):
        _seed_runs(store)
        assert RunQuery(store).count() == 6

    def test_count_with_filter(self, store):
        _seed_runs(store)
        assert RunQuery(store).outcome(RunOutcome.SUCCESS).count() == 4

    def test_first(self, store):
        _seed_runs(store)
        result = RunQuery(store).first()
        assert result is not None
        assert isinstance(result, RunRecord)

    def test_first_empty(self, store):
        result = RunQuery(store).first()
        assert result is None

    def test_metric_values(self, store):
        _seed_runs(store)
        values = RunQuery(store).metric_values("turns_total")
        assert len(values) == 6
        assert all(v == 3.0 for v in values)

    def test_stats(self, store):
        _seed_runs(store)
        s = RunQuery(store).stats("turns_total")
        assert s.mean == pytest.approx(3.0)
        assert s.count == 6


# ── Grouping ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRunQueryGrouping:
    def test_group_by_model(self, store):
        _seed_runs(store)
        groups = RunQuery(store).group_by_model()
        assert "gpt-4.1" in groups
        assert "claude-sonnet-4" in groups
        assert len(groups["gpt-4.1"]) == 4
        assert len(groups["claude-sonnet-4"]) == 2

    def test_group_by_scenario(self, store):
        _seed_runs(store)
        groups = RunQuery(store).group_by_scenario()
        assert "sc_a" in groups
        assert "sc_b" in groups
        assert "sc_c" in groups

    def test_group_by_outcome(self, store):
        _seed_runs(store)
        groups = RunQuery(store).group_by_outcome()
        assert "success" in groups
        assert len(groups["success"]) == 4


# ── Tag-based queries ────────────────────────────────────────────────


@pytest.mark.unit
class TestRunQueryTags:
    def test_tag_filter(self, store):
        _seed_runs(store)
        store.add_tag("r1", "env", "prod")
        store.add_tag("r2", "env", "prod")
        store.add_tag("r3", "env", "staging")

        runs = RunQuery(store).tag("env", "prod").execute()
        assert len(runs) == 2
        assert {r.run_id for r in runs} == {"r1", "r2"}

    def test_tag_key_only(self, store):
        _seed_runs(store)
        store.add_tag("r1", "priority", "high")
        store.add_tag("r4", "priority", "low")

        runs = RunQuery(store).tag("priority").execute()
        assert len(runs) == 2
