"""Unit tests for metrics.py — Iteration 2 derived metrics framework.

Tests for:
  - _find_metric()
  - ratio_metric()
  - difference_metric()
  - product_metric()
  - threshold_metric()
  - composite_metric()
  - Auto-registered derived metrics (cost_per_turn, tokens_per_turn, tool_calls_per_turn)
"""

from datetime import timedelta

import pytest

from codeupipe.ai.eval.metrics import (
    _find_metric,
    composite_metric,
    compute_all,
    difference_metric,
    product_metric,
    ratio_metric,
    threshold_metric,
)
from codeupipe.ai.eval.types import (
    Metric,
    RunConfig,
    RunOutcome,
    RunRecord,
    TurnSnapshot,
    _utcnow,
)


def _make_run(metrics: tuple[Metric, ...] = (), turns: int = 3) -> RunRecord:
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
        run_id="test-run",
        config=RunConfig(model="gpt-4.1"),
        outcome=RunOutcome.SUCCESS,
        started_at=now,
        ended_at=now + timedelta(seconds=5),
        turns=turn_list,
        metrics=metrics,
    )


# ── _find_metric ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestFindMetric:
    def test_found(self):
        m = Metric(name="x", value=42.0, unit="count")
        run = _make_run(metrics=(m,))
        assert _find_metric(run, "x") == 42.0

    def test_not_found(self):
        run = _make_run()
        assert _find_metric(run, "nonexistent") is None

    def test_first_match(self):
        m1 = Metric(name="x", value=1.0, unit="count")
        m2 = Metric(name="x", value=2.0, unit="count")
        run = _make_run(metrics=(m1, m2))
        assert _find_metric(run, "x") == 1.0


# ── ratio_metric ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestRatioMetric:
    def test_basic(self):
        fn = ratio_metric("r", "a", "b", unit="ratio")
        run = _make_run(metrics=(
            Metric(name="a", value=10.0, unit="x"),
            Metric(name="b", value=5.0, unit="x"),
        ))
        result = fn(run)
        assert len(result) == 1
        assert result[0].name == "r"
        assert result[0].value == pytest.approx(2.0)
        assert result[0].unit == "ratio"

    def test_denominator_zero(self):
        fn = ratio_metric("r", "a", "b", default=-1.0)
        run = _make_run(metrics=(
            Metric(name="a", value=10.0, unit="x"),
            Metric(name="b", value=0.0, unit="x"),
        ))
        result = fn(run)
        assert result[0].value == pytest.approx(-1.0)

    def test_missing_metric_uses_default(self):
        fn = ratio_metric("r", "a", "missing", default=99.0)
        run = _make_run(metrics=(
            Metric(name="a", value=10.0, unit="x"),
        ))
        result = fn(run)
        assert result[0].value == pytest.approx(99.0)


# ── difference_metric ────────────────────────────────────────────────


@pytest.mark.unit
class TestDifferenceMetric:
    def test_basic(self):
        fn = difference_metric("d", "a", "b")
        run = _make_run(metrics=(
            Metric(name="a", value=10.0, unit="x"),
            Metric(name="b", value=3.0, unit="x"),
        ))
        result = fn(run)
        assert len(result) == 1
        assert result[0].value == pytest.approx(7.0)

    def test_negative_result(self):
        fn = difference_metric("d", "a", "b")
        run = _make_run(metrics=(
            Metric(name="a", value=3.0, unit="x"),
            Metric(name="b", value=10.0, unit="x"),
        ))
        assert fn(run)[0].value == pytest.approx(-7.0)

    def test_missing_metric(self):
        fn = difference_metric("d", "a", "missing")
        run = _make_run(metrics=(
            Metric(name="a", value=10.0, unit="x"),
        ))
        assert fn(run) == []


# ── product_metric ────────────────────────────────────────────────────


@pytest.mark.unit
class TestProductMetric:
    def test_basic(self):
        fn = product_metric("p", "a", "b")
        run = _make_run(metrics=(
            Metric(name="a", value=4.0, unit="x"),
            Metric(name="b", value=5.0, unit="x"),
        ))
        assert fn(run)[0].value == pytest.approx(20.0)

    def test_zero_factor(self):
        fn = product_metric("p", "a", "b")
        run = _make_run(metrics=(
            Metric(name="a", value=0.0, unit="x"),
            Metric(name="b", value=5.0, unit="x"),
        ))
        assert fn(run)[0].value == pytest.approx(0.0)

    def test_missing_metric(self):
        fn = product_metric("p", "a", "missing")
        run = _make_run(metrics=(
            Metric(name="a", value=10.0, unit="x"),
        ))
        assert fn(run) == []


# ── threshold_metric ──────────────────────────────────────────────────


@pytest.mark.unit
class TestThresholdMetric:
    def test_above_threshold(self):
        fn = threshold_metric("t", "val", threshold=5.0, above=True)
        run = _make_run(metrics=(
            Metric(name="val", value=10.0, unit="x"),
        ))
        assert fn(run)[0].value == pytest.approx(1.0)

    def test_below_threshold(self):
        fn = threshold_metric("t", "val", threshold=5.0, above=True)
        run = _make_run(metrics=(
            Metric(name="val", value=3.0, unit="x"),
        ))
        assert fn(run)[0].value == pytest.approx(0.0)

    def test_below_mode(self):
        fn = threshold_metric("t", "val", threshold=5.0, above=False)
        run = _make_run(metrics=(
            Metric(name="val", value=3.0, unit="x"),
        ))
        assert fn(run)[0].value == pytest.approx(1.0)

    def test_exact_threshold(self):
        fn = threshold_metric("t", "val", threshold=5.0, above=True)
        run = _make_run(metrics=(
            Metric(name="val", value=5.0, unit="x"),
        ))
        # 5.0 is NOT above 5.0
        assert fn(run)[0].value == pytest.approx(0.0)

    def test_missing_source(self):
        fn = threshold_metric("t", "missing", threshold=5.0)
        run = _make_run()
        assert fn(run) == []


# ── composite_metric ──────────────────────────────────────────────────


@pytest.mark.unit
class TestCompositeMetric:
    def test_basic(self):
        fn = composite_metric("c", {"a": 0.5, "b": 0.5})
        run = _make_run(metrics=(
            Metric(name="a", value=10.0, unit="x"),
            Metric(name="b", value=20.0, unit="x"),
        ))
        result = fn(run)
        # weighted_sum = 10*0.5 + 20*0.5 = 15
        # total_weight = 0.5 + 0.5 = 1.0
        # value = 15 / 1.0 = 15.0
        assert result[0].value == pytest.approx(15.0)

    def test_unequal_weights(self):
        fn = composite_metric("c", {"a": 0.7, "b": 0.3})
        run = _make_run(metrics=(
            Metric(name="a", value=100.0, unit="x"),
            Metric(name="b", value=0.0, unit="x"),
        ))
        # weighted_sum = 100*0.7 + 0*0.3 = 70
        # total_weight = 0.7 + 0.3 = 1.0
        assert fn(run)[0].value == pytest.approx(70.0)

    def test_negative_weights(self):
        fn = composite_metric("c", {"a": 0.5, "b": -0.5})
        run = _make_run(metrics=(
            Metric(name="a", value=100.0, unit="x"),
            Metric(name="b", value=80.0, unit="x"),
        ))
        # weighted_sum = 100*0.5 + 80*(-0.5) = 50 - 40 = 10
        # total_weight = 0.5 + 0.5 = 1.0
        assert fn(run)[0].value == pytest.approx(10.0)

    def test_missing_all_components(self):
        fn = composite_metric("c", {"missing1": 0.5, "missing2": 0.5})
        run = _make_run()
        assert fn(run) == []

    def test_partial_components(self):
        fn = composite_metric("c", {"a": 0.5, "missing": 0.5})
        run = _make_run(metrics=(
            Metric(name="a", value=10.0, unit="x"),
        ))
        # Only 'a' found: weighted_sum = 10*0.5 = 5, total_weight = 0.5
        assert fn(run)[0].value == pytest.approx(10.0)


# ── Auto-registered derived metrics ──────────────────────────────────


@pytest.mark.unit
class TestAutoRegisteredDerived:
    """Verify auto-registered derived metrics produce values via compute_all."""

    def test_cost_per_turn_in_compute_all(self):
        run = _make_run(
            metrics=(
                Metric(name="cost_premium_requests", value=6.0, unit="premium_requests"),
                Metric(name="turns_total", value=3.0, unit="count"),
            ),
            turns=3,
        )
        all_metrics = compute_all(run)
        names = [m.name for m in all_metrics]
        assert "cost_per_turn" in names
        cpt = next(m for m in all_metrics if m.name == "cost_per_turn")
        assert cpt.value == pytest.approx(2.0)

    def test_tokens_per_turn_in_compute_all(self):
        run = _make_run(
            metrics=(
                Metric(name="tokens_total", value=300.0, unit="tokens"),
                Metric(name="turns_total", value=3.0, unit="count"),
            ),
            turns=3,
        )
        all_metrics = compute_all(run)
        tpt = next(m for m in all_metrics if m.name == "tokens_per_turn")
        assert tpt.value == pytest.approx(100.0)

    def test_tool_calls_per_turn_in_compute_all(self):
        run = _make_run(
            metrics=(
                Metric(name="tool_calls_total", value=9.0, unit="count"),
                Metric(name="turns_total", value=3.0, unit="count"),
            ),
            turns=3,
        )
        all_metrics = compute_all(run)
        tcpt = next(m for m in all_metrics if m.name == "tool_calls_per_turn")
        assert tcpt.value == pytest.approx(3.0)
