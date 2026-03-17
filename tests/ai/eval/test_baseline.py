"""Unit tests for codeupipe.ai.eval.baseline — control group management."""

import pytest

from codeupipe.ai.eval.baseline import (
    LOWER_IS_BETTER,
    check_regression,
    compare_to_baseline,
    establish_baseline,
)
from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    Baseline,
    Metric,
    RunConfig,
    RunOutcome,
    RunRecord,
    TurnSnapshot,
    _utcnow,
)


@pytest.fixture
def store(tmp_path):
    s = EvalStore(tmp_path / "baseline_test.db")
    yield s
    s.close()


def _make_run(
    run_id: str,
    *,
    turns: int = 3,
    tokens: int = 100,
    cost: float = 2.0,
    outcome: RunOutcome = RunOutcome.SUCCESS,
) -> RunRecord:
    """Build a RunRecord with specific metric values."""
    now = _utcnow()
    turn_list = tuple(
        TurnSnapshot(
            iteration=i,
            turn_type="follow_up",
            input_prompt="test",
            tokens_estimated=tokens,
        )
        for i in range(turns)
    )
    return RunRecord(
        run_id=run_id,
        config=RunConfig(model="gpt-4.1"),
        started_at=now,
        ended_at=now,
        outcome=outcome,
        turns=turn_list,
        metrics=(
            Metric(name="turns_total", value=float(turns)),
            Metric(name="tokens_total", value=float(tokens * turns)),
            Metric(name="cost_premium_requests", value=cost),
            Metric(name="tool_calls_total", value=2.0),
            Metric(name="score_pass_rate", value=100.0),
        ),
    )


@pytest.mark.unit
class TestEstablishBaseline:
    """Tests for baseline creation."""

    def test_from_runs(self, store):
        runs = [
            _make_run("r1", turns=3, cost=2.0),
            _make_run("r2", turns=5, cost=3.0),
            _make_run("r3", turns=4, cost=2.5),
        ]
        for r in runs:
            store.save_run(r)

        baseline = establish_baseline(store, "default", runs=runs)

        assert baseline.name == "default"
        assert baseline.run_count == 3
        assert baseline.metrics["turns_total"] == 4.0  # mean of 3,5,4
        assert baseline.metrics["cost_premium_requests"] == 2.5  # mean of 2,3,2.5

    def test_from_store(self, store):
        for i in range(5):
            run = _make_run(f"r{i}", turns=3)
            store.save_run(run)

        # Must filter to find the runs
        baseline = establish_baseline(store, "from_store")
        assert baseline.run_count == 5

    def test_persisted_to_store(self, store):
        runs = [_make_run("r1"), _make_run("r2")]
        for r in runs:
            store.save_run(r)

        baseline = establish_baseline(store, "test_persist", runs=runs)

        # Should be retrievable
        loaded = store.get_baseline(baseline.baseline_id)
        assert loaded is not None
        assert loaded.name == "test_persist"

    def test_empty_runs_raises(self, store):
        with pytest.raises(ValueError, match="No runs found"):
            establish_baseline(store, "empty", runs=[])

    def test_run_ids_tracked(self, store):
        runs = [_make_run("r1"), _make_run("r2"), _make_run("r3")]
        for r in runs:
            store.save_run(r)

        baseline = establish_baseline(store, "tracked", runs=runs)
        assert set(baseline.run_ids) == {"r1", "r2", "r3"}


@pytest.mark.unit
class TestCompareToBaseline:
    """Tests for comparing experimental runs against a baseline."""

    def test_improvement(self, store):
        # Baseline: 4 turns avg
        baseline_runs = [
            _make_run("br1", turns=4, cost=3.0),
            _make_run("br2", turns=4, cost=3.0),
        ]
        for r in baseline_runs:
            store.save_run(r)

        baseline = establish_baseline(store, "control", runs=baseline_runs)

        # Experimental: 2 turns avg (improvement for lower-is-better)
        exp_runs = [
            _make_run("er1", turns=2, cost=1.0),
            _make_run("er2", turns=2, cost=1.0),
        ]
        for r in exp_runs:
            store.save_run(r)

        results = compare_to_baseline(store, baseline, exp_runs)
        assert len(results) > 0

        # Find turns_total comparison
        turns_result = next(
            (r for r in results if r.metric_name == "turns_total"), None
        )
        assert turns_result is not None
        assert turns_result.improved is True  # lower is better for turns

    def test_regression(self, store):
        baseline_runs = [_make_run("br1", turns=2, cost=1.0)]
        for r in baseline_runs:
            store.save_run(r)

        baseline = establish_baseline(store, "control", runs=baseline_runs)

        # Worse: more turns, higher cost
        exp_runs = [_make_run("er1", turns=8, cost=5.0)]
        for r in exp_runs:
            store.save_run(r)

        results = compare_to_baseline(store, baseline, exp_runs)

        turns_result = next(
            (r for r in results if r.metric_name == "turns_total"), None
        )
        assert turns_result is not None
        assert turns_result.improved is False  # more turns = regression

    def test_specific_metrics(self, store):
        baseline_runs = [_make_run("br1")]
        for r in baseline_runs:
            store.save_run(r)

        baseline = establish_baseline(store, "control", runs=baseline_runs)
        exp_runs = [_make_run("er1")]
        for r in exp_runs:
            store.save_run(r)

        # Only compare specific metrics
        results = compare_to_baseline(
            store, baseline, exp_runs,
            metric_names=["turns_total"],
        )
        assert len(results) == 1
        assert results[0].metric_name == "turns_total"


@pytest.mark.unit
class TestCheckRegression:
    """Tests for quick regression checking."""

    def test_no_regression(self):
        baseline = Baseline(
            name="control",
            metrics={"turns_total": 5.0, "cost_premium_requests": 3.0},
            run_count=10,
        )
        run = _make_run("test", turns=5, cost=3.0)

        regressions = check_regression(baseline, run, threshold_pct=10.0)
        assert regressions == []

    def test_turns_regression(self):
        baseline = Baseline(
            name="control",
            metrics={"turns_total": 3.0},
            run_count=10,
        )
        # turns_total is LOWER_IS_BETTER — 10 is much worse than 3
        run = _make_run("test", turns=10)
        regressions = check_regression(baseline, run, threshold_pct=10.0)
        assert "turns_total" in regressions

    def test_cost_regression(self):
        baseline = Baseline(
            name="control",
            metrics={"cost_premium_requests": 2.0},
            run_count=10,
        )
        # cost is LOWER_IS_BETTER — 10.0 is much worse than 2.0
        run = _make_run("test", cost=10.0)
        regressions = check_regression(baseline, run, threshold_pct=10.0)
        assert "cost_premium_requests" in regressions

    def test_higher_is_better_regression(self):
        baseline = Baseline(
            name="control",
            metrics={"score_pass_rate": 95.0},
            run_count=10,
        )
        # score_pass_rate is higher-is-better — drop from 95→50 is regression
        run = RunRecord(
            run_id="test",
            config=RunConfig(),
            metrics=(
                Metric(name="score_pass_rate", value=50.0),
            ),
        )
        regressions = check_regression(baseline, run, threshold_pct=10.0)
        assert "score_pass_rate" in regressions

    def test_within_threshold(self):
        baseline = Baseline(
            name="control",
            metrics={"turns_total": 5.0},
            run_count=10,
        )
        # 5.4 is 8% higher — within 10% threshold
        run = RunRecord(
            run_id="test",
            config=RunConfig(),
            metrics=(
                Metric(name="turns_total", value=5.4),
            ),
        )
        regressions = check_regression(baseline, run, threshold_pct=10.0)
        assert "turns_total" not in regressions

    def test_zero_baseline_skipped(self):
        baseline = Baseline(
            name="control",
            metrics={"turns_total": 0.0},
            run_count=10,
        )
        run = _make_run("test", turns=5)
        regressions = check_regression(baseline, run, threshold_pct=10.0)
        assert "turns_total" not in regressions


@pytest.mark.unit
class TestLowerIsBetter:
    """Tests for the LOWER_IS_BETTER set."""

    def test_turns_lower_is_better(self):
        assert "turns_total" in LOWER_IS_BETTER

    def test_cost_lower_is_better(self):
        assert "cost_premium_requests" in LOWER_IS_BETTER

    def test_errors_lower_is_better(self):
        assert "errors_total" in LOWER_IS_BETTER

    def test_duration_lower_is_better(self):
        assert "duration_total_ms" in LOWER_IS_BETTER

    def test_score_not_in_set(self):
        assert "score_pass_rate" not in LOWER_IS_BETTER
