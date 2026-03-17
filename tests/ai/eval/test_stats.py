"""Unit tests for codeupipe.ai.eval.stats — pure statistical functions."""

import math

import pytest

from codeupipe.ai.eval.stats import (
    ComparisonResult,
    DescriptiveStats,
    cohens_d,
    compare,
    confidence_interval,
    describe,
    effect_size_label,
    iqr,
    max_val,
    mean,
    median,
    min_val,
    percent_change,
    percentile,
    stddev,
    value_range,
    variance,
)


@pytest.mark.unit
class TestMean:
    def test_basic(self):
        assert mean([1, 2, 3]) == 2.0

    def test_single(self):
        assert mean([5.0]) == 5.0

    def test_empty(self):
        assert mean([]) == 0.0

    def test_negative(self):
        assert mean([-1, 1]) == 0.0


@pytest.mark.unit
class TestMedian:
    def test_odd(self):
        assert median([3, 1, 2]) == 2.0

    def test_even(self):
        assert median([1, 2, 3, 4]) == 2.5

    def test_single(self):
        assert median([7]) == 7.0

    def test_empty(self):
        assert median([]) == 0.0


@pytest.mark.unit
class TestVariance:
    def test_sample_variance(self):
        vals = [2, 4, 4, 4, 5, 5, 7, 9]
        v = variance(vals, sample=True)
        assert round(v, 2) == 4.57

    def test_population_variance(self):
        vals = [2, 4, 4, 4, 5, 5, 7, 9]
        v = variance(vals, sample=False)
        assert round(v, 2) == 4.0

    def test_single_value(self):
        assert variance([5.0]) == 0.0

    def test_empty(self):
        assert variance([]) == 0.0


@pytest.mark.unit
class TestStddev:
    def test_basic(self):
        vals = [2, 4, 4, 4, 5, 5, 7, 9]
        sd = stddev(vals)
        assert round(sd, 2) == 2.14

    def test_zero_variance(self):
        assert stddev([3, 3, 3, 3]) == 0.0


@pytest.mark.unit
class TestPercentile:
    def test_p50_is_median(self):
        vals = [1, 2, 3, 4, 5]
        assert percentile(vals, 50) == 3.0

    def test_p0(self):
        assert percentile([10, 20, 30], 0) == 10

    def test_p100(self):
        assert percentile([10, 20, 30], 100) == 30

    def test_interpolation(self):
        vals = [1, 2, 3, 4]
        p25 = percentile(vals, 25)
        assert 1 < p25 < 3

    def test_empty(self):
        assert percentile([], 50) == 0.0


@pytest.mark.unit
class TestIQR:
    def test_basic(self):
        vals = [1, 2, 3, 4, 5, 6, 7, 8]
        r = iqr(vals)
        assert r > 0

    def test_empty(self):
        assert iqr([]) == 0.0


@pytest.mark.unit
class TestMinMaxRange:
    def test_min(self):
        assert min_val([3, 1, 2]) == 1

    def test_max(self):
        assert max_val([3, 1, 2]) == 3

    def test_range(self):
        assert value_range([1, 5]) == 4

    def test_empty(self):
        assert min_val([]) == 0.0
        assert max_val([]) == 0.0
        assert value_range([]) == 0.0


@pytest.mark.unit
class TestConfidenceInterval:
    def test_95_percent(self):
        vals = [10, 12, 11, 13, 10, 11, 12, 11]
        low, high = confidence_interval(vals, 0.95)
        m = mean(vals)
        assert low < m < high

    def test_single_value(self):
        low, high = confidence_interval([5.0])
        assert low == 5.0
        assert high == 5.0

    def test_empty(self):
        low, high = confidence_interval([])
        assert low == 0.0
        assert high == 0.0

    def test_wider_at_99(self):
        vals = [10, 11, 12, 13, 14]
        low95, high95 = confidence_interval(vals, 0.95)
        low99, high99 = confidence_interval(vals, 0.99)
        width95 = high95 - low95
        width99 = high99 - low99
        assert width99 > width95


@pytest.mark.unit
class TestPercentChange:
    def test_increase(self):
        assert percent_change(100, 150) == 50.0

    def test_decrease(self):
        assert percent_change(100, 50) == -50.0

    def test_no_change(self):
        assert percent_change(100, 100) == 0.0

    def test_zero_baseline(self):
        assert percent_change(0, 100) == 0.0


@pytest.mark.unit
class TestCohensD:
    def test_large_effect(self):
        a = [1, 2, 3, 4, 5]
        b = [10, 11, 12, 13, 14]
        d = cohens_d(a, b)
        assert d > 0.8  # large effect

    def test_no_effect(self):
        a = [5, 5, 5, 5, 5]
        b = [5, 5, 5, 5, 5]
        d = cohens_d(a, b)
        assert d == 0.0

    def test_insufficient_data(self):
        assert cohens_d([1], [2]) == 0.0
        assert cohens_d([], []) == 0.0


@pytest.mark.unit
class TestEffectSizeLabel:
    def test_negligible(self):
        assert effect_size_label(0.1) == "negligible"

    def test_small(self):
        assert effect_size_label(0.3) == "small"

    def test_medium(self):
        assert effect_size_label(0.6) == "medium"

    def test_large(self):
        assert effect_size_label(1.0) == "large"

    def test_negative(self):
        assert effect_size_label(-0.9) == "large"


@pytest.mark.unit
class TestDescribe:
    def test_basic(self):
        vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        stats = describe(vals)
        assert stats.count == 10
        assert stats.mean == 5.5
        assert stats.median == 5.5
        assert stats.min == 1.0
        assert stats.max == 10.0
        assert stats.stddev > 0
        assert stats.iqr > 0
        assert stats.ci_lower < stats.mean < stats.ci_upper

    def test_empty(self):
        stats = describe([])
        assert stats.count == 0
        assert stats.mean == 0.0

    def test_single(self):
        stats = describe([42.0])
        assert stats.count == 1
        assert stats.mean == 42.0
        assert stats.stddev == 0.0

    def test_to_dict(self):
        stats = describe([1, 2, 3])
        d = stats.to_dict()
        assert "mean" in d
        assert "median" in d
        assert "p95" in d


@pytest.mark.unit
class TestCompare:
    def test_improvement(self):
        baseline = [1.0, 2.0, 3.0, 4.0, 5.0]
        experimental = [6.0, 7.0, 8.0, 9.0, 10.0]
        result = compare("test_metric", baseline, experimental, higher_is_better=True)

        assert result.metric_name == "test_metric"
        assert result.percent_change > 0
        assert result.improved is True
        assert result.cohens_d > 0
        assert result.higher_is_better is True

    def test_regression(self):
        baseline = [6.0, 7.0, 8.0, 9.0, 10.0]
        experimental = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = compare("test_metric", baseline, experimental, higher_is_better=True)

        assert result.percent_change < 0
        assert result.improved is False

    def test_lower_is_better(self):
        baseline = [10.0, 11.0, 12.0, 13.0, 14.0]
        experimental = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = compare("cost", baseline, experimental, higher_is_better=False)

        assert result.improved is True  # lower is better

    def test_to_dict(self):
        result = compare("m", [1, 2, 3], [4, 5, 6])
        d = result.to_dict()
        assert d["metric_name"] == "m"
        assert "baseline" in d
        assert "experimental" in d
