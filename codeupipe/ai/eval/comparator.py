"""Comparator — Structured comparison engine for evaluation runs.

Bridges the gap between raw analytics and human decisions.
Takes two sets of runs (or a baseline + experimental set) and
produces a comprehensive, structured comparison covering every
dimension: metrics, timing, tools, outcomes, and trends.

Usage:
    from codeupipe.ai.eval.comparator import (
        RunSetComparison, compare_run_sets, rank_configs,
        regression_alert, MetricDelta,
    )

    comp = compare_run_sets(baseline_runs, experimental_runs)
    print(comp.summary)
    for delta in comp.regressions:
        print(f"REGRESSION: {delta.metric} dropped {delta.pct_change:.1f}%")
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from codeupipe.ai.eval.stats import (
    ComparisonResult,
    DescriptiveStats,
    compare,
    describe,
    welch_t_test,
)
from codeupipe.ai.eval.types import Metric, RunRecord

logger = logging.getLogger("codeupipe.ai.eval.comparator")


# ── Which metrics are "lower is better" ──────────────────────────────

LOWER_IS_BETTER: frozenset[str] = frozenset({
    "turns_total",
    "tool_calls_total",
    "tool_calls_failed",
    "tokens_total",
    "tokens_input_estimated",
    "tokens_output_estimated",
    "duration_total_ms",
    "duration_per_turn_ms",
    "duration_per_tool_ms",
    "cost_requests_total",
    "cost_premium_requests",
    "cost_multiplier",
    "errors_total",
    "context_utilization",
    "cost_per_turn",
})


# ── MetricDelta — one metric's change between two sets ────────────────

@dataclass(frozen=True)
class MetricDelta:
    """A single metric's change between baseline and experimental."""

    metric: str
    baseline: DescriptiveStats
    experimental: DescriptiveStats
    pct_change: float = 0.0
    cohens_d: float = 0.0
    effect_label: str = ""
    improved: bool = False
    significant: bool = False
    p_value: float = 1.0

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "baseline_mean": self.baseline.mean,
            "experimental_mean": self.experimental.mean,
            "pct_change": self.pct_change,
            "cohens_d": self.cohens_d,
            "effect_label": self.effect_label,
            "improved": self.improved,
            "significant": self.significant,
            "p_value": self.p_value,
        }


# ── OutcomeSummary — outcome distribution comparison ──────────────────

@dataclass(frozen=True)
class OutcomeSummary:
    """Outcome distribution for a run set."""

    total: int = 0
    success: int = 0
    failure: int = 0
    timeout: int = 0
    error: int = 0
    success_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "success": self.success,
            "failure": self.failure,
            "timeout": self.timeout,
            "error": self.error,
            "success_rate": self.success_rate,
        }


def _outcome_summary(runs: list[RunRecord]) -> OutcomeSummary:
    total = len(runs)
    if total == 0:
        return OutcomeSummary()
    success = sum(1 for r in runs if str(r.outcome) == "success")
    failure = sum(1 for r in runs if str(r.outcome) == "failure")
    timeout = sum(1 for r in runs if str(r.outcome) == "timeout")
    error = sum(1 for r in runs if str(r.outcome) == "error")
    return OutcomeSummary(
        total=total,
        success=success,
        failure=failure,
        timeout=timeout,
        error=error,
        success_rate=(success / total * 100.0),
    )


# ── RunSetComparison — the full comparison result ─────────────────────

@dataclass
class RunSetComparison:
    """Full structured comparison between two sets of runs.

    Contains metric deltas, outcome summaries, regressions,
    improvements, and a human-readable summary.
    """

    label_a: str = "Baseline"
    label_b: str = "Experimental"
    outcome_a: OutcomeSummary = field(default_factory=OutcomeSummary)
    outcome_b: OutcomeSummary = field(default_factory=OutcomeSummary)
    deltas: list[MetricDelta] = field(default_factory=list)
    regressions: list[MetricDelta] = field(default_factory=list)
    improvements: list[MetricDelta] = field(default_factory=list)
    neutral: list[MetricDelta] = field(default_factory=list)
    summary: str = ""

    @property
    def regression_count(self) -> int:
        return len(self.regressions)

    @property
    def improvement_count(self) -> int:
        return len(self.improvements)

    @property
    def has_regressions(self) -> bool:
        return self.regression_count > 0

    def to_dict(self) -> dict:
        return {
            "label_a": self.label_a,
            "label_b": self.label_b,
            "outcome_a": self.outcome_a.to_dict(),
            "outcome_b": self.outcome_b.to_dict(),
            "deltas": [d.to_dict() for d in self.deltas],
            "regressions": [d.to_dict() for d in self.regressions],
            "improvements": [d.to_dict() for d in self.improvements],
            "neutral": [d.to_dict() for d in self.neutral],
            "summary": self.summary,
        }


# ── Core comparison function ──────────────────────────────────────────

def compare_run_sets(
    runs_a: list[RunRecord],
    runs_b: list[RunRecord],
    *,
    label_a: str = "Baseline",
    label_b: str = "Experimental",
    significance_threshold: float = 0.05,
    regression_pct: float = 5.0,
) -> RunSetComparison:
    """Compare two sets of runs comprehensively.

    Args:
        runs_a: Baseline / control runs.
        runs_b: Experimental / treatment runs.
        label_a: Human label for set A.
        label_b: Human label for set B.
        significance_threshold: p-value threshold for statistical significance.
        regression_pct: Minimum percent change to classify as regression/improvement.

    Returns:
        RunSetComparison with all deltas, regressions, improvements.
    """
    # Outcome summaries
    outcome_a = _outcome_summary(runs_a)
    outcome_b = _outcome_summary(runs_b)

    # Collect metric values
    metrics_a: dict[str, list[float]] = defaultdict(list)
    metrics_b: dict[str, list[float]] = defaultdict(list)

    for run in runs_a:
        for m in run.metrics:
            metrics_a[m.name].append(m.value)
    for run in runs_b:
        for m in run.metrics:
            metrics_b[m.name].append(m.value)

    # Compare all shared metrics
    shared = sorted(set(metrics_a.keys()) & set(metrics_b.keys()))
    deltas: list[MetricDelta] = []
    regressions: list[MetricDelta] = []
    improvements: list[MetricDelta] = []
    neutral: list[MetricDelta] = []

    for name in shared:
        vals_a = metrics_a[name]
        vals_b = metrics_b[name]
        higher_is_better = name not in LOWER_IS_BETTER

        comp = compare(name, vals_a, vals_b, higher_is_better=higher_is_better)

        # Statistical significance via Welch's t-test
        p_value = 1.0
        significant = False
        if len(vals_a) >= 2 and len(vals_b) >= 2:
            hyp = welch_t_test(vals_a, vals_b)
            p_value = hyp.p_value
            significant = p_value < significance_threshold

        delta = MetricDelta(
            metric=name,
            baseline=comp.baseline_stats,
            experimental=comp.experimental_stats,
            pct_change=comp.percent_change,
            cohens_d=comp.cohens_d,
            effect_label=comp.effect_label,
            improved=comp.improved,
            significant=significant,
            p_value=p_value,
        )
        deltas.append(delta)

        # Classify
        abs_change = abs(comp.percent_change)
        if abs_change < regression_pct:
            neutral.append(delta)
        elif comp.improved:
            improvements.append(delta)
        else:
            regressions.append(delta)

    # Sort by impact
    regressions.sort(key=lambda d: abs(d.pct_change), reverse=True)
    improvements.sort(key=lambda d: abs(d.pct_change), reverse=True)

    # Generate summary
    summary_lines = [
        f"{label_a} ({outcome_a.total} runs) vs {label_b} ({outcome_b.total} runs):",
        f"  Success rate: {outcome_a.success_rate:.1f}% → {outcome_b.success_rate:.1f}%",
        f"  Metrics compared: {len(deltas)}",
        f"  Improved: {len(improvements)}, Regressed: {len(regressions)}, Neutral: {len(neutral)}",
    ]
    if regressions:
        summary_lines.append("  Top regressions:")
        for d in regressions[:3]:
            summary_lines.append(f"    - {d.metric}: {d.pct_change:+.1f}%")
    if improvements:
        summary_lines.append("  Top improvements:")
        for d in improvements[:3]:
            summary_lines.append(f"    - {d.metric}: {d.pct_change:+.1f}%")

    return RunSetComparison(
        label_a=label_a,
        label_b=label_b,
        outcome_a=outcome_a,
        outcome_b=outcome_b,
        deltas=deltas,
        regressions=regressions,
        improvements=improvements,
        neutral=neutral,
        summary="\n".join(summary_lines),
    )


# ── Rank multiple configs ─────────────────────────────────────────────

@dataclass(frozen=True)
class ConfigRanking:
    """A single config's ranking summary."""

    label: str
    run_count: int = 0
    success_rate: float = 0.0
    metric_means: dict[str, float] = field(default_factory=dict)
    rank: int = 0
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "run_count": self.run_count,
            "success_rate": self.success_rate,
            "metric_means": dict(self.metric_means),
            "rank": self.rank,
            "score": self.score,
        }


def rank_configs(
    runs_by_config: dict[str, list[RunRecord]],
    *,
    rank_by: str = "cost_premium_requests",
    higher_is_better: bool | None = None,
) -> list[ConfigRanking]:
    """Rank multiple configs by a single metric.

    Args:
        runs_by_config: Maps config_label → list of runs.
        rank_by: Metric name to rank on.
        higher_is_better: Override direction. If None, inferred from
            LOWER_IS_BETTER set.

    Returns:
        List of ConfigRanking sorted by rank (1 = best).
    """
    if higher_is_better is None:
        higher_is_better = rank_by not in LOWER_IS_BETTER

    rankings: list[ConfigRanking] = []
    for label, runs in runs_by_config.items():
        outcome = _outcome_summary(runs)

        # Compute metric means
        metric_vals: dict[str, list[float]] = defaultdict(list)
        for run in runs:
            for m in run.metrics:
                metric_vals[m.name].append(m.value)

        metric_means = {
            name: sum(vals) / len(vals)
            for name, vals in metric_vals.items()
            if vals
        }

        rankings.append(ConfigRanking(
            label=label,
            run_count=len(runs),
            success_rate=outcome.success_rate,
            metric_means=metric_means,
            score=metric_means.get(rank_by, 0.0),
        ))

    # Sort by score
    rankings.sort(
        key=lambda r: r.score,
        reverse=higher_is_better,
    )

    # Assign ranks
    ranked = []
    for i, r in enumerate(rankings):
        ranked.append(ConfigRanking(
            label=r.label,
            run_count=r.run_count,
            success_rate=r.success_rate,
            metric_means=r.metric_means,
            rank=i + 1,
            score=r.score,
        ))

    return ranked


# ── Regression alert ──────────────────────────────────────────────────

@dataclass(frozen=True)
class RegressionAlert:
    """An actionable regression alert."""

    metric: str
    baseline_mean: float
    current_mean: float
    pct_change: float
    severity: str  # "warning" | "critical"
    message: str

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "baseline_mean": self.baseline_mean,
            "current_mean": self.current_mean,
            "pct_change": self.pct_change,
            "severity": self.severity,
            "message": self.message,
        }


def regression_alert(
    comparison: RunSetComparison,
    *,
    warning_pct: float = 10.0,
    critical_pct: float = 25.0,
) -> list[RegressionAlert]:
    """Generate actionable regression alerts from a comparison.

    Args:
        comparison: A completed run set comparison.
        warning_pct: Percent change threshold for warning severity.
        critical_pct: Percent change threshold for critical severity.

    Returns:
        List of RegressionAlert, sorted by severity (critical first).
    """
    alerts: list[RegressionAlert] = []

    for delta in comparison.regressions:
        abs_change = abs(delta.pct_change)
        if abs_change < warning_pct:
            continue

        severity = "critical" if abs_change >= critical_pct else "warning"
        msg = (
            f"{delta.metric} regressed {delta.pct_change:+.1f}% "
            f"({delta.baseline.mean:.2f} → {delta.experimental.mean:.2f})"
        )
        if delta.significant:
            msg += " [statistically significant]"

        alerts.append(RegressionAlert(
            metric=delta.metric,
            baseline_mean=delta.baseline.mean,
            current_mean=delta.experimental.mean,
            pct_change=delta.pct_change,
            severity=severity,
            message=msg,
        ))

    # Critical first, then by magnitude
    alerts.sort(key=lambda a: (0 if a.severity == "critical" else 1, -abs(a.pct_change)))
    return alerts
