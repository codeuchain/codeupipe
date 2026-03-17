"""Pure statistical functions — no external dependencies.

All functions operate on plain lists of floats so they're usable
anywhere in the eval framework without importing numpy/scipy.
When statistical libraries are available they can wrap these for
richer analysis, but the core math lives here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable


# ── Basic descriptors ─────────────────────────────────────────────────

def mean(values: list[float]) -> float:
    """Arithmetic mean."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def median(values: list[float]) -> float:
    """Median (middle value or average of two middle values)."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return s[mid]


def variance(values: list[float], *, sample: bool = True) -> float:
    """Variance (Bessel-corrected sample variance by default)."""
    if len(values) < 2:
        return 0.0
    m = mean(values)
    ss = sum((x - m) ** 2 for x in values)
    denom = len(values) - 1 if sample else len(values)
    return ss / denom


def stddev(values: list[float], *, sample: bool = True) -> float:
    """Standard deviation."""
    return math.sqrt(variance(values, sample=sample))


def percentile(values: list[float], p: float) -> float:
    """Percentile (0–100).  Uses linear interpolation."""
    if not values:
        return 0.0
    s = sorted(values)
    if p <= 0:
        return s[0]
    if p >= 100:
        return s[-1]
    k = (len(s) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def iqr(values: list[float]) -> float:
    """Interquartile range (P75 − P25)."""
    return percentile(values, 75) - percentile(values, 25)


# ── Min / Max / Range ─────────────────────────────────────────────────

def min_val(values: list[float]) -> float:
    return min(values) if values else 0.0


def max_val(values: list[float]) -> float:
    return max(values) if values else 0.0


def value_range(values: list[float]) -> float:
    if not values:
        return 0.0
    return max(values) - min(values)


# ── Confidence interval ──────────────────────────────────────────────

# Z-scores for common confidence levels
_Z_TABLE: dict[float, float] = {
    0.80: 1.282,
    0.90: 1.645,
    0.95: 1.960,
    0.99: 2.576,
}


def confidence_interval(
    values: list[float],
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Confidence interval for the mean (normal approximation).

    Returns (lower_bound, upper_bound).
    """
    if len(values) < 2:
        m = mean(values)
        return (m, m)

    m = mean(values)
    se = stddev(values) / math.sqrt(len(values))
    z = _Z_TABLE.get(confidence, 1.960)
    return (m - z * se, m + z * se)


# ── Comparison ────────────────────────────────────────────────────────

def percent_change(baseline: float, experimental: float) -> float:
    """Percentage change from baseline to experimental.

    Returns 0.0 if baseline is zero.
    """
    if baseline == 0.0:
        return 0.0
    return ((experimental - baseline) / abs(baseline)) * 100.0


def cohens_d(group_a: list[float], group_b: list[float]) -> float:
    """Cohen's d effect size between two groups.

    Uses pooled standard deviation.  Returns 0.0 if either
    group has fewer than 2 values.
    """
    if len(group_a) < 2 or len(group_b) < 2:
        return 0.0
    m_a = mean(group_a)
    m_b = mean(group_b)
    var_a = variance(group_a)
    var_b = variance(group_b)
    n_a = len(group_a)
    n_b = len(group_b)
    pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)
    pooled_sd = math.sqrt(pooled_var)
    if pooled_sd == 0.0:
        return 0.0
    return (m_b - m_a) / pooled_sd


def effect_size_label(d: float) -> str:
    """Human-readable label for Cohen's d magnitude."""
    d = abs(d)
    if d < 0.2:
        return "negligible"
    if d < 0.5:
        return "small"
    if d < 0.8:
        return "medium"
    return "large"


# ── Summary ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DescriptiveStats:
    """Full descriptive statistics for a list of values."""

    count: int = 0
    mean: float = 0.0
    median: float = 0.0
    stddev: float = 0.0
    min: float = 0.0
    max: float = 0.0
    p25: float = 0.0
    p75: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    iqr: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "stddev": self.stddev,
            "min": self.min,
            "max": self.max,
            "p25": self.p25,
            "p75": self.p75,
            "p95": self.p95,
            "p99": self.p99,
            "iqr": self.iqr,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
        }


def describe(values: list[float], confidence: float = 0.95) -> DescriptiveStats:
    """Compute full descriptive statistics for a list of values."""
    if not values:
        return DescriptiveStats()

    ci = confidence_interval(values, confidence)
    return DescriptiveStats(
        count=len(values),
        mean=mean(values),
        median=median(values),
        stddev=stddev(values) if len(values) >= 2 else 0.0,
        min=min_val(values),
        max=max_val(values),
        p25=percentile(values, 25),
        p75=percentile(values, 75),
        p95=percentile(values, 95),
        p99=percentile(values, 99),
        iqr=iqr(values),
        ci_lower=ci[0],
        ci_upper=ci[1],
    )


@dataclass(frozen=True)
class ComparisonResult:
    """Statistical comparison between a baseline group and experimental group."""

    metric_name: str = ""
    baseline_stats: DescriptiveStats = field(default_factory=DescriptiveStats)
    experimental_stats: DescriptiveStats = field(default_factory=DescriptiveStats)
    percent_change: float = 0.0
    cohens_d: float = 0.0
    effect_label: str = "negligible"
    improved: bool = False
    higher_is_better: bool = True

    def to_dict(self) -> dict:
        return {
            "metric_name": self.metric_name,
            "baseline": self.baseline_stats.to_dict(),
            "experimental": self.experimental_stats.to_dict(),
            "percent_change": self.percent_change,
            "cohens_d": self.cohens_d,
            "effect_label": self.effect_label,
            "improved": self.improved,
            "higher_is_better": self.higher_is_better,
        }


def compare(
    metric_name: str,
    baseline_values: list[float],
    experimental_values: list[float],
    *,
    higher_is_better: bool = True,
) -> ComparisonResult:
    """Compare two groups of metric values statistically."""
    b_stats = describe(baseline_values)
    e_stats = describe(experimental_values)
    pct = percent_change(b_stats.mean, e_stats.mean)
    d = cohens_d(baseline_values, experimental_values)
    improved = (pct > 0) if higher_is_better else (pct < 0)

    return ComparisonResult(
        metric_name=metric_name,
        baseline_stats=b_stats,
        experimental_stats=e_stats,
        percent_change=pct,
        cohens_d=d,
        effect_label=effect_size_label(d),
        improved=improved,
        higher_is_better=higher_is_better,
    )


# ── Correlation ───────────────────────────────────────────────────────


def pearson_r(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient between two equal-length lists.

    Returns a value between -1.0 and 1.0.
    Returns 0.0 if either list has fewer than 2 values
    or if standard deviation is zero.
    """
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    mx = mean(x)
    my = mean(y)
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den_x = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    den_y = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if den_x == 0.0 or den_y == 0.0:
        return 0.0
    return num / (den_x * den_y)


def spearman_rho(x: list[float], y: list[float]) -> float:
    """Spearman rank correlation coefficient.

    Converts values to ranks (average-rank for ties) and computes
    Pearson r on the ranks.  More robust to non-linear relationships.
    """
    if len(x) != len(y) or len(x) < 2:
        return 0.0

    def _ranks(vals: list[float]) -> list[float]:
        indexed = sorted(enumerate(vals), key=lambda t: t[1])
        ranks = [0.0] * len(vals)
        i = 0
        while i < len(indexed):
            j = i
            while j < len(indexed) and indexed[j][1] == indexed[i][1]:
                j += 1
            avg_rank = (i + 1 + j) / 2.0  # 1-based average
            for k in range(i, j):
                ranks[indexed[k][0]] = avg_rank
            i = j
        return ranks

    return pearson_r(_ranks(x), _ranks(y))


def correlation_label(r: float) -> str:
    """Human-readable label for correlation magnitude."""
    r = abs(r)
    if r < 0.1:
        return "negligible"
    if r < 0.3:
        return "weak"
    if r < 0.5:
        return "moderate"
    if r < 0.7:
        return "strong"
    return "very strong"


@dataclass(frozen=True)
class CorrelationResult:
    """Correlation between two metric series."""

    metric_a: str = ""
    metric_b: str = ""
    pearson: float = 0.0
    spearman: float = 0.0
    label: str = "negligible"
    n: int = 0

    def to_dict(self) -> dict:
        return {
            "metric_a": self.metric_a,
            "metric_b": self.metric_b,
            "pearson": self.pearson,
            "spearman": self.spearman,
            "label": self.label,
            "n": self.n,
        }


def correlate(
    metric_a: str,
    values_a: list[float],
    metric_b: str,
    values_b: list[float],
) -> CorrelationResult:
    """Compute Pearson and Spearman correlation between two metric series."""
    p = pearson_r(values_a, values_b)
    s = spearman_rho(values_a, values_b)
    return CorrelationResult(
        metric_a=metric_a,
        metric_b=metric_b,
        pearson=p,
        spearman=s,
        label=correlation_label(p),
        n=min(len(values_a), len(values_b)),
    )


def correlation_matrix(
    named_values: dict[str, list[float]],
) -> dict[tuple[str, str], CorrelationResult]:
    """Compute pairwise Pearson/Spearman correlations for all metric pairs.

    Returns a dict keyed by (metric_a, metric_b) for a < b
    (lexicographic ordering avoids duplicate pairs).
    """
    names = sorted(named_values.keys())
    results: dict[tuple[str, str], CorrelationResult] = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            results[(a, b)] = correlate(a, named_values[a], b, named_values[b])
    return results


# ── Hypothesis Testing ───────────────────────────────────────────────


@dataclass(frozen=True)
class HypothesisResult:
    """Result of a statistical hypothesis test."""

    test_name: str = ""
    statistic: float = 0.0
    p_value: float = 1.0
    significant: bool = False
    alpha: float = 0.05
    effect_size: float = 0.0
    effect_label: str = "negligible"
    n_a: int = 0
    n_b: int = 0

    def to_dict(self) -> dict:
        return {
            "test_name": self.test_name,
            "statistic": self.statistic,
            "p_value": self.p_value,
            "significant": self.significant,
            "alpha": self.alpha,
            "effect_size": self.effect_size,
            "effect_label": self.effect_label,
            "n_a": self.n_a,
            "n_b": self.n_b,
        }


def _t_cdf_approx(t_val: float, df: float) -> float:
    """Approximate cumulative distribution function for Student's t.

    Uses a rational approximation (Abramowitz & Stegun 26.2.17)
    for the normal CDF, adjusted for df via the relationship
    t ~ N(0,1) as df → ∞.

    For df ≥ 30, uses direct normal approximation.
    For smaller df, applies Cornish-Fisher correction.
    """
    if df <= 0:
        return 0.5

    # Convert t to z using approximation for finite df
    if df >= 30:
        z = t_val
    else:
        # Cornish-Fisher approximation: t ≈ z * (1 + (z² + 1) / (4*df))
        # Invert: z ≈ t / (1 + (t² + 1) / (4*df))
        z = t_val / (1.0 + (t_val ** 2 + 1.0) / (4.0 * df))

    # Standard normal CDF approximation (Abramowitz & Stegun)
    return _normal_cdf(z)


def _normal_cdf(z: float) -> float:
    """Standard normal CDF approximation.

    Accurate to ~1e-5.  Uses the Abramowitz & Stegun
    error function approximation.
    """
    # erf-based: Φ(z) = 0.5 * (1 + erf(z / √2))
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def welch_t_test(
    group_a: list[float],
    group_b: list[float],
    *,
    alpha: float = 0.05,
) -> HypothesisResult:
    """Welch's t-test for independent samples (unequal variances).

    Tests H0: mean(A) = mean(B) vs H1: mean(A) ≠ mean(B).
    Does NOT assume equal variances or equal sample sizes.
    """
    n_a = len(group_a)
    n_b = len(group_b)
    if n_a < 2 or n_b < 2:
        return HypothesisResult(
            test_name="welch_t",
            n_a=n_a, n_b=n_b, alpha=alpha,
        )

    m_a = mean(group_a)
    m_b = mean(group_b)
    v_a = variance(group_a)
    v_b = variance(group_b)

    se = math.sqrt(v_a / n_a + v_b / n_b)
    if se == 0.0:
        return HypothesisResult(
            test_name="welch_t",
            n_a=n_a, n_b=n_b, alpha=alpha,
        )

    t_stat = (m_a - m_b) / se

    # Welch-Satterthwaite degrees of freedom
    num = (v_a / n_a + v_b / n_b) ** 2
    den = (v_a / n_a) ** 2 / (n_a - 1) + (v_b / n_b) ** 2 / (n_b - 1)
    df = num / den if den > 0 else 1.0

    # Two-tailed p-value
    p = 2.0 * (1.0 - _t_cdf_approx(abs(t_stat), df))
    p = max(0.0, min(1.0, p))

    d = cohens_d(group_a, group_b)

    return HypothesisResult(
        test_name="welch_t",
        statistic=t_stat,
        p_value=p,
        significant=p < alpha,
        alpha=alpha,
        effect_size=d,
        effect_label=effect_size_label(d),
        n_a=n_a,
        n_b=n_b,
    )


def mann_whitney_u(
    group_a: list[float],
    group_b: list[float],
    *,
    alpha: float = 0.05,
) -> HypothesisResult:
    """Mann-Whitney U test (non-parametric alternative to t-test).

    Does not assume normality.  Tests whether one group tends
    to have larger values than the other.

    Uses normal approximation for p-value (accurate for n ≥ 8).
    """
    n_a = len(group_a)
    n_b = len(group_b)
    if n_a < 1 or n_b < 1:
        return HypothesisResult(
            test_name="mann_whitney_u",
            n_a=n_a, n_b=n_b, alpha=alpha,
        )

    # Count: for each a_i, how many b_j < a_i (and ties)
    u_a = 0.0
    for a_val in group_a:
        for b_val in group_b:
            if b_val < a_val:
                u_a += 1.0
            elif b_val == a_val:
                u_a += 0.5

    u_b = n_a * n_b - u_a
    u_stat = min(u_a, u_b)

    # Normal approximation
    mu = n_a * n_b / 2.0
    sigma = math.sqrt(n_a * n_b * (n_a + n_b + 1) / 12.0)

    if sigma == 0.0:
        return HypothesisResult(
            test_name="mann_whitney_u",
            statistic=u_stat,
            n_a=n_a, n_b=n_b, alpha=alpha,
        )

    z = (u_stat - mu) / sigma
    p = 2.0 * _normal_cdf(z)  # two-tailed (z is negative for extreme U)
    p = max(0.0, min(1.0, p))

    d = cohens_d(group_a, group_b) if n_a >= 2 and n_b >= 2 else 0.0

    return HypothesisResult(
        test_name="mann_whitney_u",
        statistic=u_stat,
        p_value=p,
        significant=p < alpha,
        alpha=alpha,
        effect_size=d,
        effect_label=effect_size_label(d),
        n_a=n_a,
        n_b=n_b,
    )


def bootstrap_ci(
    values: list[float],
    *,
    n_resamples: int = 1000,
    confidence: float = 0.95,
    statistic_fn: Callable[[list[float]], float] | None = None,
    seed: int = 42,
) -> tuple[float, float]:
    """Bootstrap confidence interval for a statistic.

    Resamples with replacement ``n_resamples`` times and returns
    the (lower, upper) bounds at the given confidence level.

    Default statistic is the mean.  Pass a custom function for
    median, trimmed mean, etc.

    Uses a deterministic seed for reproducibility.
    """
    import random
    if not values:
        return (0.0, 0.0)

    fn = statistic_fn or mean
    rng = random.Random(seed)

    bootstrap_stats: list[float] = []
    for _ in range(n_resamples):
        sample = rng.choices(values, k=len(values))
        bootstrap_stats.append(fn(sample))

    bootstrap_stats.sort()
    lower_idx = int((1.0 - confidence) / 2.0 * n_resamples)
    upper_idx = int((1.0 + confidence) / 2.0 * n_resamples) - 1
    lower_idx = max(0, min(lower_idx, n_resamples - 1))
    upper_idx = max(0, min(upper_idx, n_resamples - 1))

    return (bootstrap_stats[lower_idx], bootstrap_stats[upper_idx])


# ── Anomaly Detection ────────────────────────────────────────────────


@dataclass(frozen=True)
class AnomalyResult:
    """Result of anomaly detection for a single value."""

    value: float = 0.0
    z_score: float = 0.0
    is_outlier_zscore: bool = False
    is_outlier_iqr: bool = False
    is_anomaly: bool = False
    method: str = ""

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "z_score": self.z_score,
            "is_outlier_zscore": self.is_outlier_zscore,
            "is_outlier_iqr": self.is_outlier_iqr,
            "is_anomaly": self.is_anomaly,
            "method": self.method,
        }


def z_score(value: float, values: list[float]) -> float:
    """Z-score of a single value within a distribution."""
    if len(values) < 2:
        return 0.0
    m = mean(values)
    s = stddev(values)
    if s == 0.0:
        return 0.0
    return (value - m) / s


def detect_outliers_zscore(
    values: list[float],
    *,
    threshold: float = 2.5,
) -> list[int]:
    """Return indices of values that are Z-score outliers.

    Default threshold of 2.5 catches values beyond ~99.4% of
    a normal distribution.
    """
    if len(values) < 3:
        return []
    m = mean(values)
    s = stddev(values)
    if s == 0.0:
        return []
    return [
        i for i, v in enumerate(values)
        if abs((v - m) / s) > threshold
    ]


def detect_outliers_iqr(
    values: list[float],
    *,
    factor: float = 1.5,
) -> list[int]:
    """Return indices of values outside the IQR fence.

    Classic Tukey fence: values below Q1 - factor*IQR or
    above Q3 + factor*IQR are outliers.
    """
    if len(values) < 4:
        return []
    q1 = percentile(values, 25)
    q3 = percentile(values, 75)
    iq = q3 - q1
    lower = q1 - factor * iq
    upper = q3 + factor * iq
    return [i for i, v in enumerate(values) if v < lower or v > upper]


def detect_anomaly(
    value: float,
    reference: list[float],
    *,
    z_threshold: float = 2.5,
    iqr_factor: float = 1.5,
) -> AnomalyResult:
    """Check if a single value is anomalous relative to a reference set.

    Uses both Z-score and IQR methods.  Flags as anomaly if
    either method triggers.
    """
    z = z_score(value, reference)
    is_z = abs(z) > z_threshold

    is_iqr = False
    if len(reference) >= 4:
        q1 = percentile(reference, 25)
        q3 = percentile(reference, 75)
        iq = q3 - q1
        lower = q1 - iqr_factor * iq
        upper = q3 + iqr_factor * iq
        is_iqr = value < lower or value > upper

    methods: list[str] = []
    if is_z:
        methods.append("zscore")
    if is_iqr:
        methods.append("iqr")

    return AnomalyResult(
        value=value,
        z_score=z,
        is_outlier_zscore=is_z,
        is_outlier_iqr=is_iqr,
        is_anomaly=is_z or is_iqr,
        method="+".join(methods) if methods else "none",
    )


# ── Trend Analysis ───────────────────────────────────────────────────


@dataclass(frozen=True)
class TrendResult:
    """Result of trend analysis on a time-ordered series."""

    slope: float = 0.0
    intercept: float = 0.0
    direction: str = "flat"  # "improving", "degrading", "flat"
    r_squared: float = 0.0
    moving_avg: tuple[float, ...] = ()
    rate_of_change: tuple[float, ...] = ()

    def to_dict(self) -> dict:
        return {
            "slope": self.slope,
            "intercept": self.intercept,
            "direction": self.direction,
            "r_squared": self.r_squared,
            "moving_avg": list(self.moving_avg),
            "rate_of_change": list(self.rate_of_change),
        }


def linear_regression(x: list[float], y: list[float]) -> tuple[float, float]:
    """Simple linear regression: y = slope * x + intercept.

    Returns (slope, intercept).
    """
    n = len(x)
    if n < 2 or len(y) != n:
        return (0.0, 0.0)

    mx = mean(x)
    my = mean(y)
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = sum((xi - mx) ** 2 for xi in x)
    if den == 0.0:
        return (0.0, my)
    slope = num / den
    intercept = my - slope * mx
    return (slope, intercept)


def r_squared(x: list[float], y: list[float]) -> float:
    """Coefficient of determination (R²) for linear fit.

    Measures how well the linear regression explains variance.
    """
    if len(x) < 2 or len(y) != len(x):
        return 0.0
    slope, intercept = linear_regression(x, y)
    y_pred = [slope * xi + intercept for xi in x]
    my = mean(y)
    ss_res = sum((yi - yp) ** 2 for yi, yp in zip(y, y_pred))
    ss_tot = sum((yi - my) ** 2 for yi in y)
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return 1.0 - ss_res / ss_tot


def moving_average(values: list[float], window: int = 3) -> list[float]:
    """Simple moving average with the given window size."""
    if not values or window < 1:
        return []
    if window > len(values):
        window = len(values)
    result: list[float] = []
    for i in range(len(values) - window + 1):
        window_vals = values[i: i + window]
        result.append(sum(window_vals) / len(window_vals))
    return result


def rate_of_change(values: list[float]) -> list[float]:
    """Point-to-point rate of change (percentage).

    Returns a list with len(values) - 1 elements.
    """
    if len(values) < 2:
        return []
    changes: list[float] = []
    for i in range(1, len(values)):
        if values[i - 1] == 0.0:
            changes.append(0.0)
        else:
            changes.append(
                ((values[i] - values[i - 1]) / abs(values[i - 1])) * 100.0
            )
    return changes


def analyze_trend(
    values: list[float],
    *,
    higher_is_better: bool = True,
    min_slope: float = 0.01,
    window: int = 3,
) -> TrendResult:
    """Full trend analysis on an ordered series.

    Computes linear regression, R², moving average, and
    rate of change.  Classifies the trend as improving,
    degrading, or flat based on slope direction and R².
    """
    if not values:
        return TrendResult()

    x = list(range(len(values)))
    xf = [float(v) for v in x]

    slope, intercept = linear_regression(xf, values)
    r2 = r_squared(xf, values)
    ma = moving_average(values, window=window)
    roc = rate_of_change(values)

    # Determine direction
    if abs(slope) < min_slope or r2 < 0.1:
        direction = "flat"
    elif higher_is_better:
        direction = "improving" if slope > 0 else "degrading"
    else:
        direction = "improving" if slope < 0 else "degrading"

    return TrendResult(
        slope=slope,
        intercept=intercept,
        direction=direction,
        r_squared=r2,
        moving_avg=tuple(ma),
        rate_of_change=tuple(roc),
    )
