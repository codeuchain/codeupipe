"""Unit tests for ExperimentResult iteration 3 enhancements.

Tests: all_runs, success_rate, outcome_distribution,
       best_config, to_dict with outcomes.
"""

import pytest

from codeupipe.ai.eval.experiment import ExperimentResult
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


def _run(
    run_id: str,
    *,
    model: str = "gpt-4.1",
    outcome: RunOutcome = RunOutcome.SUCCESS,
    metrics: tuple[Metric, ...] = (),
) -> RunRecord:
    now = _utcnow()
    default_metrics = (
        Metric(name="turns_total", value=3.0),
        Metric(name="cost_premium_requests", value=2.0),
    )
    return RunRecord(
        run_id=run_id,
        config=RunConfig(model=model),
        outcome=outcome,
        started_at=now,
        ended_at=now,
        turns=(
            TurnSnapshot(
                iteration=0,
                turn_type="follow_up",
                input_prompt="test",
                tokens_estimated=100,
            ),
        ),
        metrics=metrics or default_metrics,
    )


def _experiment_result(
    runs_by_config: dict[str, list[RunRecord]] | None = None,
) -> ExperimentResult:
    exp = Experiment(
        experiment_id="exp_1",
        name="test",
        description="test",
        created_at=_utcnow(),
        configs=(RunConfig(model="gpt-4.1"),),
        scenario_ids=("sc1",),
        status=ExperimentStatus.COMPLETED,
    )
    if runs_by_config is None:
        runs_by_config = {
            "config_a": [
                _run("r1", outcome=RunOutcome.SUCCESS),
                _run("r2", outcome=RunOutcome.SUCCESS),
                _run("r3", outcome=RunOutcome.FAILURE),
            ],
            "config_b": [
                _run("r4", outcome=RunOutcome.SUCCESS),
                _run("r5", outcome=RunOutcome.TIMEOUT),
            ],
        }
    return ExperimentResult(
        experiment=exp,
        runs_by_config=runs_by_config,
    )


# ── all_runs ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAllRuns:
    def test_flat_list(self):
        er = _experiment_result()
        all_runs = er.all_runs()
        assert len(all_runs) == 5

    def test_single_config(self):
        er = _experiment_result({"a": [_run("r1")]})
        assert len(er.all_runs()) == 1

    def test_empty(self):
        er = _experiment_result({})
        assert len(er.all_runs()) == 0


# ── success_rate ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestSuccessRate:
    def test_overall(self):
        er = _experiment_result()
        # 3 successes out of 5
        rate = er.success_rate()
        assert rate == pytest.approx(60.0)

    def test_per_config(self):
        er = _experiment_result()
        # config_a: 2/3 success
        rate_a = er.success_rate("config_a")
        assert rate_a == pytest.approx(66.67, abs=0.1)
        # config_b: 1/2 success
        rate_b = er.success_rate("config_b")
        assert rate_b == pytest.approx(50.0)

    def test_nonexistent_config(self):
        er = _experiment_result()
        assert er.success_rate("nonexistent") == 0.0

    def test_all_success(self):
        er = _experiment_result({
            "a": [_run("r1"), _run("r2")],
        })
        assert er.success_rate() == pytest.approx(100.0)


# ── outcome_distribution ─────────────────────────────────────────────


@pytest.mark.unit
class TestOutcomeDistribution:
    def test_overall(self):
        er = _experiment_result()
        dist = er.outcome_distribution()
        assert dist["success"] == 3
        assert dist["failure"] == 1
        assert dist["timeout"] == 1

    def test_per_config(self):
        er = _experiment_result()
        dist_a = er.outcome_distribution("config_a")
        assert dist_a["success"] == 2
        assert dist_a["failure"] == 1

    def test_empty(self):
        er = _experiment_result({})
        dist = er.outcome_distribution()
        assert dist == {}


# ── best_config ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestBestConfig:
    def test_higher_is_better(self):
        er = _experiment_result({
            "cheap": [
                _run("r1", metrics=(Metric(name="done_naturally", value=0.5),)),
            ],
            "accurate": [
                _run("r2", metrics=(Metric(name="done_naturally", value=1.0),)),
            ],
        })
        assert er.best_config("done_naturally", higher_is_better=True) == "accurate"

    def test_lower_is_better(self):
        er = _experiment_result({
            "fast": [
                _run("r1", metrics=(Metric(name="turns_total", value=2.0),)),
            ],
            "slow": [
                _run("r2", metrics=(Metric(name="turns_total", value=8.0),)),
            ],
        })
        assert er.best_config("turns_total", higher_is_better=False) == "fast"

    def test_no_data(self):
        er = _experiment_result({})
        assert er.best_config("turns_total") == ""

    def test_metric_not_present(self):
        er = _experiment_result({
            "a": [_run("r1", metrics=())],
        })
        assert er.best_config("nonexistent") == ""


# ── to_dict ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestToDictEnhanced:
    def test_contains_standard_fields(self):
        er = _experiment_result()
        d = er.to_dict()
        assert "experiment" in d
        assert "total_runs" in d
        assert d["total_runs"] == 5
        assert "config_labels" in d

    def test_comparisons_list(self):
        er = _experiment_result()
        d = er.to_dict()
        assert isinstance(d["comparisons"], list)

    def test_scores_list(self):
        er = _experiment_result()
        d = er.to_dict()
        assert isinstance(d["scores"], list)
