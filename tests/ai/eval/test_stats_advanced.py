"""Unit tests for stats.py — Iteration 2 additions.

Tests for:
  - Correlation (Pearson, Spearman, matrix)
  - Hypothesis testing (Welch's t, Mann-Whitney U, bootstrap CI)
  - Anomaly detection (z-score, IQR, detect_anomaly)
  - Trend analysis (linear regression, R², moving average, rate of change)
"""

import math

import pytest

from codeupipe.ai.eval.stats import (
    AnomalyResult,
    CorrelationResult,
    HypothesisResult,
    TrendResult,
    analyze_trend,
    bootstrap_ci,
    correlate,
    correlation_label,
    correlation_matrix,
    detect_anomaly,
    detect_outliers_iqr,
    detect_outliers_zscore,
    linear_regression,
    mann_whitney_u,
    moving_average,
    pearson_r,
    r_squared,
    rate_of_change,
    spearman_rho,
    welch_t_test,
    z_score,
)


# ── Correlation ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestPearsonR:
    def test_perfect_positive(self):
        assert pearson_r([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)

    def test_perfect_negative(self):
        assert pearson_r([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)

    def test_no_correlation(self):
        # These are designed to have near-zero correlation
        r = pearson_r([1, 2, 3, 4, 5], [2, 4, 1, 5, 3])
        assert abs(r) < 0.5

    def test_empty(self):
        assert pearson_r([], []) == 0.0

    def test_single_value(self):
        assert pearson_r([1], [2]) == 0.0

    def test_unequal_lengths(self):
        assert pearson_r([1, 2], [1, 2, 3]) == 0.0

    def test_constant_values(self):
        assert pearson_r([5, 5, 5], [1, 2, 3]) == 0.0


@pytest.mark.unit
class TestSpearmanRho:
    def test_perfect_rank_positive(self):
        assert spearman_rho([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)

    def test_perfect_rank_negative(self):
        assert spearman_rho([1, 2, 3], [30, 20, 10]) == pytest.approx(-1.0)

    def test_with_ties(self):
        rho = spearman_rho([1, 2, 2, 3], [1, 2, 3, 4])
        assert -1.0 <= rho <= 1.0

    def test_empty(self):
        assert spearman_rho([], []) == 0.0


@pytest.mark.unit
class TestCorrelationLabel:
    def test_negligible(self):
        assert correlation_label(0.05) == "negligible"

    def test_weak(self):
        assert correlation_label(0.2) == "weak"

    def test_moderate(self):
        assert correlation_label(0.4) == "moderate"

    def test_strong(self):
        assert correlation_label(0.6) == "strong"

    def test_very_strong(self):
        assert correlation_label(0.8) == "very strong"

    def test_negative(self):
        assert correlation_label(-0.9) == "very strong"


@pytest.mark.unit
class TestCorrelate:
    def test_returns_result(self):
        result = correlate("a", [1, 2, 3], "b", [1, 2, 3])
        assert isinstance(result, CorrelationResult)
        assert result.metric_a == "a"
        assert result.metric_b == "b"
        assert result.pearson == pytest.approx(1.0)
        assert result.n == 3

    def test_to_dict(self):
        result = correlate("x", [1, 2, 3], "y", [3, 2, 1])
        d = result.to_dict()
        assert d["metric_a"] == "x"
        assert d["pearson"] == pytest.approx(-1.0)


@pytest.mark.unit
class TestCorrelationMatrix:
    def test_basic(self):
        data = {
            "a": [1.0, 2.0, 3.0],
            "b": [1.0, 2.0, 3.0],
            "c": [3.0, 2.0, 1.0],
        }
        matrix = correlation_matrix(data)
        assert ("a", "b") in matrix
        assert ("a", "c") in matrix
        assert ("b", "c") in matrix
        assert matrix[("a", "b")].pearson == pytest.approx(1.0)
        assert matrix[("a", "c")].pearson == pytest.approx(-1.0)

    def test_single_metric(self):
        matrix = correlation_matrix({"a": [1, 2, 3]})
        assert len(matrix) == 0

    def test_empty(self):
        matrix = correlation_matrix({})
        assert len(matrix) == 0


# ── Hypothesis Testing ───────────────────────────────────────────────


@pytest.mark.unit
class TestWelchTTest:
    def test_identical_groups(self):
        result = welch_t_test([1, 2, 3], [1, 2, 3])
        assert isinstance(result, HypothesisResult)
        assert result.test_name == "welch_t"
        assert result.statistic == pytest.approx(0.0)
        assert not result.significant

    def test_different_groups(self):
        a = [1, 2, 3, 4, 5]
        b = [10, 11, 12, 13, 14]
        result = welch_t_test(a, b)
        assert result.significant
        assert result.p_value < 0.05

    def test_small_samples(self):
        result = welch_t_test([1], [2])
        assert result.n_a == 1
        assert result.p_value == 1.0  # can't test with n < 2

    def test_custom_alpha(self):
        result = welch_t_test([1, 2, 3], [4, 5, 6], alpha=0.01)
        assert result.alpha == 0.01

    def test_to_dict(self):
        result = welch_t_test([1, 2, 3], [4, 5, 6])
        d = result.to_dict()
        assert "test_name" in d
        assert "p_value" in d
        assert "significant" in d


@pytest.mark.unit
class TestMannWhitneyU:
    def test_identical_groups(self):
        result = mann_whitney_u([1, 2, 3], [1, 2, 3])
        assert isinstance(result, HypothesisResult)
        assert result.test_name == "mann_whitney_u"
        assert not result.significant

    def test_completely_separated(self):
        a = [1, 2, 3, 4, 5]
        b = [10, 11, 12, 13, 14]
        result = mann_whitney_u(a, b)
        assert result.significant
        assert result.p_value < 0.05

    def test_empty(self):
        result = mann_whitney_u([], [1, 2, 3])
        assert result.n_a == 0
        assert result.p_value == 1.0

    def test_to_dict(self):
        result = mann_whitney_u([1, 2], [3, 4])
        d = result.to_dict()
        assert d["test_name"] == "mann_whitney_u"


@pytest.mark.unit
class TestBootstrapCI:
    def test_basic(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        lower, upper = bootstrap_ci(values)
        assert lower < upper
        assert lower > 0.0
        assert upper < 6.0

    def test_deterministic(self):
        """Same seed should give same results."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        r1 = bootstrap_ci(values, seed=42)
        r2 = bootstrap_ci(values, seed=42)
        assert r1 == r2

    def test_different_seeds(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        r1 = bootstrap_ci(values, seed=42)
        r2 = bootstrap_ci(values, seed=99)
        # May differ (though could match by chance)
        # Just verify both return valid intervals
        assert r1[0] < r1[1]
        assert r2[0] < r2[1]

    def test_empty(self):
        assert bootstrap_ci([]) == (0.0, 0.0)

    def test_custom_statistic(self):
        from codeupipe.ai.eval.stats import median
        values = [1.0, 2.0, 3.0, 4.0, 100.0]
        lower, upper = bootstrap_ci(values, statistic_fn=median)
        assert lower <= upper

    def test_narrow_confidence(self):
        values = [5.0] * 20
        lower, upper = bootstrap_ci(values, confidence=0.99)
        assert lower == pytest.approx(5.0)
        assert upper == pytest.approx(5.0)


# ── Anomaly Detection ────────────────────────────────────────────────


@pytest.mark.unit
class TestZScore:
    def test_at_mean(self):
        assert z_score(5.0, [4, 5, 6]) == pytest.approx(0.0)

    def test_above_mean(self):
        z = z_score(10.0, [1, 2, 3, 4, 5])
        assert z > 0

    def test_empty_reference(self):
        assert z_score(5.0, []) == 0.0

    def test_constant_reference(self):
        assert z_score(5.0, [3, 3, 3]) == 0.0


@pytest.mark.unit
class TestDetectOutliersZScore:
    def test_no_outliers(self):
        assert detect_outliers_zscore([1, 2, 3, 4, 5]) == []

    def test_with_outlier(self):
        values = [1, 2, 3, 4, 5, 100]
        outliers = detect_outliers_zscore(values, threshold=2.0)
        assert 5 in outliers  # index 5 = value 100

    def test_too_few_values(self):
        assert detect_outliers_zscore([1, 2]) == []


@pytest.mark.unit
class TestDetectOutliersIQR:
    def test_no_outliers(self):
        assert detect_outliers_iqr([1, 2, 3, 4, 5]) == []

    def test_with_outlier(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 100]
        outliers = detect_outliers_iqr(values)
        assert 9 in outliers  # index 9 = value 100

    def test_too_few_values(self):
        assert detect_outliers_iqr([1, 2, 3]) == []


@pytest.mark.unit
class TestDetectAnomaly:
    def test_normal_value(self):
        result = detect_anomaly(3.0, [1, 2, 3, 4, 5])
        assert not result.is_anomaly

    def test_anomalous_value(self):
        ref = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = detect_anomaly(100.0, ref)
        assert result.is_anomaly
        assert result.is_outlier_zscore
        assert result.z_score > 2.5

    def test_to_dict(self):
        result = detect_anomaly(5.0, [1, 2, 3, 4, 5])
        d = result.to_dict()
        assert "value" in d
        assert "z_score" in d
        assert "is_anomaly" in d

    def test_both_methods(self):
        ref = list(range(1, 21))
        result = detect_anomaly(500.0, ref)
        assert result.is_outlier_zscore
        assert result.is_outlier_iqr
        assert "zscore" in result.method
        assert "iqr" in result.method


# ── Trend Analysis ───────────────────────────────────────────────────


@pytest.mark.unit
class TestLinearRegression:
    def test_perfect_fit(self):
        slope, intercept = linear_regression([0, 1, 2], [0, 2, 4])
        assert slope == pytest.approx(2.0)
        assert intercept == pytest.approx(0.0)

    def test_with_intercept(self):
        slope, intercept = linear_regression([0, 1, 2], [1, 2, 3])
        assert slope == pytest.approx(1.0)
        assert intercept == pytest.approx(1.0)

    def test_empty(self):
        assert linear_regression([], []) == (0.0, 0.0)

    def test_single_point(self):
        assert linear_regression([1], [5]) == (0.0, 0.0)


@pytest.mark.unit
class TestRSquared:
    def test_perfect_fit(self):
        assert r_squared([0, 1, 2], [0, 2, 4]) == pytest.approx(1.0)

    def test_no_fit(self):
        r2 = r_squared([1, 2, 3, 4, 5], [2, 4, 1, 5, 3])
        assert 0.0 <= r2 <= 1.0

    def test_empty(self):
        assert r_squared([], []) == 0.0


@pytest.mark.unit
class TestMovingAverage:
    def test_basic(self):
        result = moving_average([1, 2, 3, 4, 5], window=3)
        assert result == pytest.approx([2.0, 3.0, 4.0])

    def test_window_1(self):
        result = moving_average([1, 2, 3], window=1)
        assert result == pytest.approx([1.0, 2.0, 3.0])

    def test_window_equals_length(self):
        result = moving_average([1, 2, 3], window=3)
        assert result == pytest.approx([2.0])

    def test_window_larger_than_data(self):
        result = moving_average([1, 2], window=5)
        assert result == pytest.approx([1.5])

    def test_empty(self):
        assert moving_average([], window=3) == []


@pytest.mark.unit
class TestRateOfChange:
    def test_basic(self):
        result = rate_of_change([10, 20, 15])
        assert result[0] == pytest.approx(100.0)  # 10 → 20 = +100%
        assert result[1] == pytest.approx(-25.0)  # 20 → 15 = -25%

    def test_from_zero(self):
        result = rate_of_change([0, 10])
        assert result[0] == 0.0  # avoid division by zero

    def test_empty(self):
        assert rate_of_change([]) == []

    def test_single_value(self):
        assert rate_of_change([5]) == []


@pytest.mark.unit
class TestAnalyzeTrend:
    def test_improving_higher_is_better(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = analyze_trend(values, higher_is_better=True)
        assert isinstance(result, TrendResult)
        assert result.direction == "improving"
        assert result.slope > 0

    def test_degrading_higher_is_better(self):
        values = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = analyze_trend(values, higher_is_better=True)
        assert result.direction == "degrading"
        assert result.slope < 0

    def test_improving_lower_is_better(self):
        values = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = analyze_trend(values, higher_is_better=False)
        assert result.direction == "improving"

    def test_flat(self):
        values = [5.0, 5.0, 5.0, 5.0, 5.0]
        result = analyze_trend(values)
        assert result.direction == "flat"

    def test_empty(self):
        result = analyze_trend([])
        assert result.direction == "flat"

    def test_has_moving_avg(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = analyze_trend(values, window=3)
        assert len(result.moving_avg) == 3

    def test_has_rate_of_change(self):
        values = [1.0, 2.0, 3.0]
        result = analyze_trend(values)
        assert len(result.rate_of_change) == 2

    def test_to_dict(self):
        result = analyze_trend([1.0, 2.0, 3.0])
        d = result.to_dict()
        assert "slope" in d
        assert "direction" in d
        assert "r_squared" in d
