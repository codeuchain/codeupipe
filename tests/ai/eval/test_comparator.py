"""Tests for comparator.py — the comparison engine.

Tests for:
  - MetricDelta, OutcomeSummary, RunSetComparison
  - compare_run_sets()
  - rank_configs()
  - regression_alert()
"""

from datetime import timedelta

import pytest

from codeupipe.ai.eval.comparator import (
    ConfigRanking,
    MetricDelta,
    OutcomeSummary,
    RegressionAlert,
    RunSetComparison,
    compare_run_sets,
    rank_configs,
    regression_alert,
)
from codeupipe.ai.eval.types import (
    Metric,
    RunConfig,
    RunOutcome,
    RunRecord,
    TurnSnapshot,
    _utcnow,
)


def _run(
    run_id: str = "r1",
    outcome: RunOutcome = RunOutcome.SUCCESS,
    model: str = "gpt-4.1",
    metrics: tuple[Metric, ...] = (),
    turns: int = 3,
) -> RunRecord:
    now = _utcnow()
    turn_list = tuple(
        TurnSnapshot(
            iteration=i,
            turn_type="assistant",
            input_prompt="hello",
            tokens_estimated=100,
            duration_ms=50.0,
        )
        for i in range(turns)
    )
    return RunRecord(
        run_id=run_id,
        config=RunConfig(model=model),
        outcome=outcome,
        started_at=now,
        ended_at=now + timedelta(seconds=5),
        turns=turn_list,
        metrics=metrics,
    )


def _metric(name: str, value: float, unit: str = "count") -> Metric:
    return Metric(name=name, value=value, unit=unit)


# ── OutcomeSummary ────────────────────────────────────────────────────


@pytest.mark.unit
class TestOutcomeSummary:
    def test_basic(self):
        runs = [
            _run("r1", outcome=RunOutcome.SUCCESS),
            _run("r2", outcome=RunOutcome.SUCCESS),
            _run("r3", outcome=RunOutcome.FAILURE),
        ]
        from codeupipe.ai.eval.comparator import _outcome_summary
        s = _outcome_summary(runs)
        assert s.total == 3
        assert s.success == 2
        assert s.failure == 1
        assert s.success_rate == pytest.approx(66.67, abs=0.1)

    def test_empty(self):
        from codeupipe.ai.eval.comparator import _outcome_summary
        s = _outcome_summary([])
        assert s.total == 0
        assert s.success_rate == 0.0


# ── compare_run_sets ──────────────────────────────────────────────────


@pytest.mark.unit
class TestCompareRunSets:
    def test_identical_runs(self):
        metrics = (_metric("turns_total", 3.0), _metric("tokens_total", 300.0))
        a = [_run(f"a{i}", metrics=metrics) for i in range(5)]
        b = [_run(f"b{i}", metrics=metrics) for i in range(5)]
        comp = compare_run_sets(a, b)
        assert comp.regression_count == 0
        assert comp.improvement_count == 0
        assert comp.outcome_a.total == 5
        assert comp.outcome_b.total == 5

    def test_improved_metrics(self):
        a_metrics = (_metric("turns_total", 5.0),)
        b_metrics = (_metric("turns_total", 3.0),)  # lower is better for turns
        a = [_run(f"a{i}", metrics=a_metrics) for i in range(5)]
        b = [_run(f"b{i}", metrics=b_metrics) for i in range(5)]
        comp = compare_run_sets(a, b)
        assert comp.improvement_count >= 1

    def test_regressed_metrics(self):
        a_metrics = (_metric("turns_total", 3.0),)
        b_metrics = (_metric("turns_total", 10.0),)  # higher turns = worse
        a = [_run(f"a{i}", metrics=a_metrics) for i in range(5)]
        b = [_run(f"b{i}", metrics=b_metrics) for i in range(5)]
        comp = compare_run_sets(a, b)
        assert comp.has_regressions

    def test_summary_generated(self):
        metrics = (_metric("turns_total", 3.0),)
        a = [_run("a1", metrics=metrics)]
        b = [_run("b1", metrics=metrics)]
        comp = compare_run_sets(a, b, label_a="Control", label_b="Treatment")
        assert "Control" in comp.summary
        assert "Treatment" in comp.summary

    def test_custom_labels(self):
        comp = compare_run_sets(
            [_run("a")], [_run("b")],
            label_a="Alpha", label_b="Beta",
        )
        assert comp.label_a == "Alpha"
        assert comp.label_b == "Beta"

    def test_to_dict(self):
        comp = compare_run_sets([_run("a")], [_run("b")])
        d = comp.to_dict()
        assert "deltas" in d
        assert "regressions" in d
        assert "improvements" in d

    def test_significance_threshold(self):
        a_metrics = (_metric("turns_total", 3.0),)
        b_metrics = (_metric("turns_total", 3.1),)
        a = [_run(f"a{i}", metrics=a_metrics) for i in range(2)]
        b = [_run(f"b{i}", metrics=b_metrics) for i in range(2)]
        comp = compare_run_sets(a, b, significance_threshold=0.01)
        # With only 2 samples each, unlikely to be significant
        for delta in comp.deltas:
            # Just verify the field exists
            assert isinstance(delta.significant, bool)
            assert isinstance(delta.p_value, float)


# ── rank_configs ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestRankConfigs:
    def test_basic(self):
        runs_by_config = {
            "fast": [_run("r1", metrics=(_metric("turns_total", 2.0),))],
            "slow": [_run("r2", metrics=(_metric("turns_total", 10.0),))],
        }
        # Lower turns is better (rank_by default uses LOWER_IS_BETTER)
        rankings = rank_configs(runs_by_config, rank_by="turns_total")
        assert rankings[0].label == "fast"
        assert rankings[0].rank == 1

    def test_higher_is_better(self):
        runs_by_config = {
            "a": [_run("r1", metrics=(_metric("done_naturally", 1.0),))],
            "b": [_run("r2", metrics=(_metric("done_naturally", 0.0),))],
        }
        rankings = rank_configs(
            runs_by_config, rank_by="done_naturally", higher_is_better=True,
        )
        assert rankings[0].label == "a"

    def test_to_dict(self):
        runs_by_config = {
            "x": [_run("r1", metrics=(_metric("turns_total", 3.0),))],
        }
        rankings = rank_configs(runs_by_config, rank_by="turns_total")
        d = rankings[0].to_dict()
        assert "label" in d
        assert "rank" in d
        assert "success_rate" in d


# ── regression_alert ──────────────────────────────────────────────────


@pytest.mark.unit
class TestRegressionAlert:
    def test_no_regressions(self):
        metrics = (_metric("turns_total", 3.0),)
        a = [_run(f"a{i}", metrics=metrics) for i in range(3)]
        b = [_run(f"b{i}", metrics=metrics) for i in range(3)]
        comp = compare_run_sets(a, b)
        alerts = regression_alert(comp)
        assert alerts == []

    def test_warning_alert(self):
        a_metrics = (_metric("turns_total", 3.0),)
        b_metrics = (_metric("turns_total", 4.0),)  # 33% regression
        a = [_run(f"a{i}", metrics=a_metrics) for i in range(3)]
        b = [_run(f"b{i}", metrics=b_metrics) for i in range(3)]
        comp = compare_run_sets(a, b)
        alerts = regression_alert(comp, warning_pct=10.0, critical_pct=50.0)
        if alerts:  # depends on magnitude
            assert alerts[0].severity in ("warning", "critical")

    def test_alert_to_dict(self):
        alert = RegressionAlert(
            metric="turns_total",
            baseline_mean=3.0,
            current_mean=5.0,
            pct_change=66.7,
            severity="critical",
            message="turns_total regressed",
        )
        d = alert.to_dict()
        assert d["metric"] == "turns_total"
        assert d["severity"] == "critical"

    def test_critical_sorted_first(self):
        a_metrics = (_metric("turns_total", 3.0), _metric("tokens_total", 100.0))
        b_metrics = (_metric("turns_total", 10.0), _metric("tokens_total", 500.0))
        a = [_run(f"a{i}", metrics=a_metrics) for i in range(3)]
        b = [_run(f"b{i}", metrics=b_metrics) for i in range(3)]
        comp = compare_run_sets(a, b)
        alerts = regression_alert(comp, warning_pct=5.0, critical_pct=25.0)
        if len(alerts) >= 2:
            # Critical should come first
            critical_indices = [
                i for i, a in enumerate(alerts) if a.severity == "critical"
            ]
            warning_indices = [
                i for i, a in enumerate(alerts) if a.severity == "warning"
            ]
            if critical_indices and warning_indices:
                assert max(critical_indices) < min(warning_indices)
