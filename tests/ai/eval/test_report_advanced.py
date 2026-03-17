"""Unit tests for report.py iteration 3 additions.

Tests: experiment_report_md, trend_report_md,
       regression_report_md, dashboard_report_md.
"""

from datetime import timedelta

import pytest

from codeupipe.ai.eval.comparator import (
    RegressionAlert,
    compare_run_sets,
    regression_alert,
)
from codeupipe.ai.eval.experiment import ExperimentResult
from codeupipe.ai.eval.report import (
    experiment_report_md,
    regression_report_md,
    trend_report_md,
)
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


# ── Helpers ───────────────────────────────────────────────────────────


def _run(
    run_id: str,
    *,
    model: str = "gpt-4.1",
    outcome: RunOutcome = RunOutcome.SUCCESS,
    turns: int = 3,
    cost: float = 2.0,
    started_at=None,
) -> RunRecord:
    now = started_at or _utcnow()
    return RunRecord(
        run_id=run_id,
        config=RunConfig(model=model),
        outcome=outcome,
        started_at=now,
        ended_at=now + timedelta(seconds=5),
        turns=tuple(
            TurnSnapshot(
                iteration=i,
                turn_type="follow_up",
                input_prompt="test",
                tokens_estimated=100,
                duration_ms=50.0,
            )
            for i in range(turns)
        ),
        metrics=(
            Metric(name="turns_total", value=float(turns)),
            Metric(name="cost_premium_requests", value=cost),
            Metric(name="tokens_total", value=float(turns * 100)),
            Metric(name="done_naturally", value=1.0 if outcome == RunOutcome.SUCCESS else 0.0),
        ),
    )


def _experiment_result(
    configs: int = 2,
    runs_per: int = 3,
) -> ExperimentResult:
    exp = Experiment(
        experiment_id="exp_1",
        name="test-experiment",
        description="Testing",
        created_at=_utcnow(),
        configs=tuple(RunConfig(model=f"model_{i}") for i in range(configs)),
        scenario_ids=("sc_1",),
        status=ExperimentStatus.COMPLETED,
    )

    runs_by_config = {}
    for c in range(configs):
        label = f"config_{c}_model_{c}"
        runs_by_config[label] = [
            _run(f"run_{c}_{r}", model=f"model_{c}",
                 turns=3 + c, cost=2.0 + c * 0.5)
            for r in range(runs_per)
        ]

    return ExperimentResult(
        experiment=exp,
        runs_by_config=runs_by_config,
    )


# ── experiment_report_md ─────────────────────────────────────────────


@pytest.mark.unit
class TestExperimentReportMd:
    def test_basic_structure(self):
        er = _experiment_result()
        report = experiment_report_md(er)
        assert "# Experiment Report" in report
        assert "test-experiment" in report
        assert "exp_1" in report

    def test_config_overview_table(self):
        er = _experiment_result(configs=2)
        report = experiment_report_md(er)
        assert "Config Overview" in report
        assert "model_0" in report
        assert "model_1" in report

    def test_metrics_table(self):
        er = _experiment_result()
        report = experiment_report_md(er)
        assert "Key Metrics" in report
        assert "turns_total" in report

    def test_total_runs(self):
        er = _experiment_result(configs=2, runs_per=4)
        report = experiment_report_md(er)
        assert "8" in report  # 2 configs × 4 runs

    def test_with_scores(self):
        from codeupipe.ai.eval.scorer import ScoreResult

        er = _experiment_result()
        er.scores = [
            ScoreResult(
                run_id="run_0_0",
                weighted_average=0.8,
                pass_rate=100.0,
            ),
        ]
        report = experiment_report_md(er)
        assert "Scores" in report
        assert "run_0_0" in report

    def test_single_config(self):
        er = _experiment_result(configs=1)
        report = experiment_report_md(er)
        assert "config_0" in report


# ── trend_report_md ───────────────────────────────────────────────────


@pytest.mark.unit
class TestTrendReportMd:
    def test_basic_structure(self):
        now = _utcnow()
        runs = [
            _run(f"r{i}", started_at=now - timedelta(days=10 - i), turns=3 + i)
            for i in range(10)
        ]
        report = trend_report_md(runs)
        assert "# Metric Trend Report" in report
        assert "Runs analyzed" in report
        assert "10" in report

    def test_trend_directions(self):
        now = _utcnow()
        runs = [
            _run(f"r{i}", started_at=now - timedelta(days=20 - i), turns=3 + i)
            for i in range(15)
        ]
        report = trend_report_md(runs)
        assert "Trend Summary" in report
        assert "turns_total" in report

    def test_custom_metrics(self):
        now = _utcnow()
        runs = [
            _run(f"r{i}", started_at=now - timedelta(days=5 - i))
            for i in range(5)
        ]
        report = trend_report_md(runs, metric_names=["tokens_total"])
        assert "tokens_total" in report

    def test_insufficient_data(self):
        runs = [_run("r1")]
        report = trend_report_md(runs, metric_names=["turns_total"])
        assert "insufficient" in report.lower()

    def test_empty_runs(self):
        report = trend_report_md([])
        assert "0" in report

    def test_no_matching_metrics(self):
        runs = [_run("r1")]
        report = trend_report_md(runs, metric_names=["nonexistent"])
        assert "insufficient" in report.lower() or "No metrics" in report


# ── regression_report_md ──────────────────────────────────────────────


@pytest.mark.unit
class TestRegressionReportMd:
    def test_no_alerts(self):
        report = regression_report_md([])
        assert "No regressions" in report
        assert "Total alerts" in report

    def test_with_alerts(self):
        alerts = [
            RegressionAlert(
                metric="turns_total",
                baseline_mean=3.0,
                current_mean=6.0,
                pct_change=100.0,
                severity="critical",
                message="turns_total regressed 100%",
            ),
            RegressionAlert(
                metric="tokens_total",
                baseline_mean=300.0,
                current_mean=360.0,
                pct_change=20.0,
                severity="warning",
                message="tokens_total regressed 20%",
            ),
        ]
        report = regression_report_md(alerts)
        assert "CRITICAL" in report
        assert "turns_total" in report
        assert "warning" in report
        assert "tokens_total" in report

    def test_critical_highlighted(self):
        alerts = [
            RegressionAlert(
                metric="cost",
                baseline_mean=1.0,
                current_mean=5.0,
                pct_change=400.0,
                severity="critical",
                message="cost exploded",
            ),
        ]
        report = regression_report_md(alerts)
        assert "**CRITICAL**" in report

    def test_integrated_with_comparator(self):
        a_metrics = (Metric(name="turns_total", value=3.0),)
        b_metrics = (Metric(name="turns_total", value=10.0),)
        a = [_run(f"a{i}", turns=3) for i in range(3)]
        b = [_run(f"b{i}", turns=10) for i in range(3)]
        comp = compare_run_sets(a, b)
        alerts = regression_alert(comp, warning_pct=5.0, critical_pct=25.0)
        report = regression_report_md(alerts)
        assert "Regression Report" in report
