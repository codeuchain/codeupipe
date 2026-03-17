"""Unit tests for codeupipe.ai.eval.experiment — A/B experiment runner."""

import pytest

from codeupipe.ai.eval.experiment import ExperimentResult, compare_runs
from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    Experiment,
    ExperimentStatus,
    Metric,
    RunConfig,
    RunOutcome,
    RunRecord,
    TurnSnapshot,
    _utcnow,
)


@pytest.fixture
def store(tmp_path):
    s = EvalStore(tmp_path / "experiment_test.db")
    yield s
    s.close()


def _make_run(
    run_id: str,
    *,
    model: str = "gpt-4.1",
    turns: int = 3,
    cost: float = 2.0,
    outcome: RunOutcome = RunOutcome.SUCCESS,
) -> RunRecord:
    now = _utcnow()
    return RunRecord(
        run_id=run_id,
        config=RunConfig(model=model),
        started_at=now,
        ended_at=now,
        outcome=outcome,
        turns=tuple(
            TurnSnapshot(
                iteration=i,
                turn_type="follow_up",
                input_prompt="test",
                tokens_estimated=100,
            )
            for i in range(turns)
        ),
        metrics=(
            Metric(name="turns_total", value=float(turns)),
            Metric(name="cost_premium_requests", value=cost),
            Metric(name="tokens_total", value=float(turns * 100)),
        ),
    )


@pytest.mark.unit
class TestExperimentResult:
    """Tests for ExperimentResult helper methods."""

    def test_total_runs(self):
        result = ExperimentResult(
            experiment=Experiment(name="test"),
            runs_by_config={
                "config_a": [_make_run("r1"), _make_run("r2")],
                "config_b": [_make_run("r3")],
            },
        )
        assert result.total_runs == 3

    def test_config_labels(self):
        result = ExperimentResult(
            experiment=Experiment(name="test"),
            runs_by_config={
                "config_a": [_make_run("r1")],
                "config_b": [_make_run("r2")],
            },
        )
        labels = result.config_labels()
        assert "config_a" in labels
        assert "config_b" in labels

    def test_metric_summary(self):
        result = ExperimentResult(
            experiment=Experiment(name="test"),
            runs_by_config={
                "config_a": [
                    _make_run("r1", turns=3),
                    _make_run("r2", turns=5),
                ],
            },
        )

        summary = result.metric_summary("turns_total")
        assert "config_a" in summary
        assert summary["config_a"]["mean"] == 4.0  # avg of 3,5
        assert summary["config_a"]["count"] == 2

    def test_to_dict(self):
        result = ExperimentResult(
            experiment=Experiment(name="test"),
            runs_by_config={"a": [_make_run("r1")]},
        )
        d = result.to_dict()
        assert d["total_runs"] == 1
        assert "experiment" in d


@pytest.mark.unit
class TestCompareRuns:
    """Tests for quick head-to-head comparison."""

    def test_basic_comparison(self):
        runs_a = [
            _make_run("a1", turns=3, cost=2.0),
            _make_run("a2", turns=4, cost=3.0),
        ]
        runs_b = [
            _make_run("b1", turns=2, cost=1.0),
            _make_run("b2", turns=2, cost=1.0),
        ]

        results = compare_runs(runs_a, runs_b)
        assert "turns_total" in results
        assert "cost_premium_requests" in results

        # B is better (lower turns, lower cost)
        turns = results["turns_total"]
        assert turns.improved is True  # turns is lower-is-better

    def test_shared_metrics_only(self):
        """Only metrics present in both groups are compared."""
        run_a = RunRecord(
            run_id="a",
            config=RunConfig(),
            metrics=(
                Metric(name="shared", value=1.0),
                Metric(name="only_a", value=2.0),
            ),
        )
        run_b = RunRecord(
            run_id="b",
            config=RunConfig(),
            metrics=(
                Metric(name="shared", value=3.0),
                Metric(name="only_b", value=4.0),
            ),
        )

        results = compare_runs([run_a], [run_b])
        assert "shared" in results
        assert "only_a" not in results
        assert "only_b" not in results

    def test_empty_groups(self):
        results = compare_runs([], [])
        assert results == {}
