"""Unit tests for EvalStore lifecycle management methods.

Tests: delete_run, purge_before, list_experiments,
       delete_experiment, delete_baseline, database_stats, vacuum.
"""

from datetime import timedelta

import pytest

from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    Baseline,
    Experiment,
    ExperimentStatus,
    Metric,
    RawEvent,
    RunConfig,
    RunOutcome,
    RunRecord,
    ToolCallRecord,
    TurnSnapshot,
    _new_id,
    _utcnow,
)


@pytest.fixture
def store(tmp_path):
    s = EvalStore(tmp_path / "lifecycle_test.db")
    yield s
    s.close()


def _make_run(
    run_id: str = "r1",
    *,
    outcome: RunOutcome = RunOutcome.SUCCESS,
    started_at=None,
) -> RunRecord:
    now = started_at or _utcnow()
    return RunRecord(
        run_id=run_id,
        config=RunConfig(model="gpt-4.1"),
        outcome=outcome,
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
        tool_calls=(
            ToolCallRecord(
                tool_name="read_file",
                server_name="fs",
                iteration=0,
                success=True,
                duration_ms=10.0,
            ),
        ),
        metrics=(
            Metric(name="turns_total", value=1.0),
            Metric(name="tokens_total", value=100.0),
        ),
    )


def _make_experiment(
    experiment_id: str = "exp_1",
    *,
    status: ExperimentStatus = ExperimentStatus.COMPLETED,
    name: str = "test-experiment",
) -> Experiment:
    return Experiment(
        experiment_id=experiment_id,
        name=name,
        description="Test",
        created_at=_utcnow(),
        configs=(RunConfig(model="gpt-4.1"),),
        scenario_ids=("sc_1",),
        status=status,
    )


# ── delete_run ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDeleteRun:
    def test_deletes_existing_run(self, store):
        store.save_run(_make_run("r1"))
        assert store.get_run("r1") is not None
        assert store.delete_run("r1") is True
        assert store.get_run("r1") is None

    def test_returns_false_for_nonexistent(self, store):
        assert store.delete_run("nonexistent") is False

    def test_cascading_delete(self, store):
        run = _make_run("r1")
        store.save_run(run)

        # Add tags and annotations
        store.add_tag("r1", "env", "prod")
        store.add_annotation("r1", "test annotation", author="test")

        # Add raw event
        event = RawEvent(
            event_id="ev1",
            run_id="r1",
            event_type="test",
            timestamp=_utcnow(),
            payload={"key": "value"},
        )
        store.save_raw_event(event)

        # Delete and verify everything is gone
        assert store.delete_run("r1") is True
        assert store.get_run("r1") is None

        # Tags should be gone
        runs_by_tag = store.list_runs_by_tag("env", "prod")
        assert len(runs_by_tag) == 0

    def test_doesnt_affect_other_runs(self, store):
        store.save_run(_make_run("r1"))
        store.save_run(_make_run("r2"))
        store.delete_run("r1")
        assert store.get_run("r1") is None
        assert store.get_run("r2") is not None


# ── purge_before ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestPurgeBefore:
    def test_purges_old_runs(self, store):
        now = _utcnow()
        store.save_run(_make_run("old", started_at=now - timedelta(days=30)))
        store.save_run(_make_run("recent", started_at=now - timedelta(hours=1)))

        count = store.purge_before(now - timedelta(days=7))
        assert count == 1
        assert store.get_run("old") is None
        assert store.get_run("recent") is not None

    def test_purge_nothing(self, store):
        now = _utcnow()
        store.save_run(_make_run("r1", started_at=now))
        count = store.purge_before(now - timedelta(days=365))
        assert count == 0

    def test_purge_all(self, store):
        now = _utcnow()
        store.save_run(_make_run("r1", started_at=now - timedelta(days=5)))
        store.save_run(_make_run("r2", started_at=now - timedelta(days=3)))
        count = store.purge_before(now)
        assert count == 2
        assert store.count_runs() == 0


# ── list_experiments ──────────────────────────────────────────────────


@pytest.mark.unit
class TestListExperiments:
    def test_list_all(self, store):
        store.save_experiment(_make_experiment("exp_1"))
        store.save_experiment(_make_experiment("exp_2"))
        experiments = store.list_experiments()
        assert len(experiments) == 2

    def test_filter_by_status(self, store):
        store.save_experiment(
            _make_experiment("exp_1", status=ExperimentStatus.COMPLETED)
        )
        store.save_experiment(
            _make_experiment("exp_2", status=ExperimentStatus.RUNNING)
        )
        completed = store.list_experiments(status="completed")
        assert len(completed) == 1
        assert completed[0].experiment_id == "exp_1"

    def test_limit(self, store):
        for i in range(5):
            store.save_experiment(_make_experiment(f"exp_{i}"))
        experiments = store.list_experiments(limit=2)
        assert len(experiments) == 2

    def test_empty(self, store):
        experiments = store.list_experiments()
        assert experiments == []


# ── delete_experiment ─────────────────────────────────────────────────


@pytest.mark.unit
class TestDeleteExperiment:
    def test_deletes_existing(self, store):
        store.save_experiment(_make_experiment("exp_1"))
        assert store.delete_experiment("exp_1") is True
        assert store.get_experiment("exp_1") is None

    def test_returns_false_for_nonexistent(self, store):
        assert store.delete_experiment("nonexistent") is False


# ── delete_baseline ───────────────────────────────────────────────────


@pytest.mark.unit
class TestDeleteBaseline:
    def test_deletes_existing(self, store):
        baseline = Baseline(
            baseline_id="bl_1",
            name="test-baseline",
            created_at=_utcnow(),
            config=RunConfig(model="gpt-4.1"),
            run_count=5,
            metrics={"turns_total": 3.0},
        )
        store.save_baseline(baseline)
        assert store.delete_baseline("bl_1") is True
        assert store.get_baseline("bl_1") is None

    def test_returns_false_for_nonexistent(self, store):
        assert store.delete_baseline("nonexistent") is False


# ── database_stats ────────────────────────────────────────────────────


@pytest.mark.unit
class TestDatabaseStats:
    def test_empty_database(self, store):
        stats = store.database_stats()
        assert stats["runs"] == 0
        assert stats["turns"] == 0
        assert stats["tool_calls"] == 0
        assert stats["metrics"] == 0
        assert len(stats) == 10

    def test_with_data(self, store):
        store.save_run(_make_run("r1"))
        stats = store.database_stats()
        assert stats["runs"] == 1
        assert stats["turns"] == 1
        assert stats["tool_calls"] == 1
        assert stats["metrics"] == 2

    def test_all_tables_present(self, store):
        stats = store.database_stats()
        expected_tables = {
            "runs", "turns", "tool_calls", "metrics",
            "raw_events", "scenarios", "baselines",
            "experiments", "tags", "annotations",
        }
        assert set(stats.keys()) == expected_tables


# ── vacuum ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestVacuum:
    def test_vacuum_succeeds(self, store):
        store.save_run(_make_run("r1"))
        store.delete_run("r1")
        store.vacuum()  # Should not raise

    def test_vacuum_empty_db(self, store):
        store.vacuum()  # Should not raise
