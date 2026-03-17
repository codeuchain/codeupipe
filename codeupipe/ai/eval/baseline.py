"""Baseline — Establish and compare against control groups.

A baseline is the scientific control: run N times with a fixed
config, aggregate the metrics, save the result.  All future
experiments compare against this reference point.

Usage:
    store = EvalStore("eval.db")

    # Establish a baseline from existing runs
    baseline = establish_baseline(
        store,
        name="gpt-4.1-default",
        scenario_id="sc_abc123",
    )

    # Compare new runs against the baseline
    report = compare_to_baseline(store, baseline, new_runs)
"""

from __future__ import annotations

import logging
from collections import defaultdict

from codeupipe.ai.eval.stats import (
    ComparisonResult,
    compare,
    describe,
)
from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    Baseline,
    RunConfig,
    RunRecord,
    _new_id,
    _utcnow,
)

logger = logging.getLogger("codeupipe.ai.eval.baseline")


# ── Metrics we care about for baselines ───────────────────────────────

# Metrics where lower is better
LOWER_IS_BETTER: frozenset[str] = frozenset({
    "turns_total",
    "tool_calls_failed",
    "cost_premium_requests",
    "cost_requests_total",
    "duration_total_ms",
    "duration_per_turn_ms",
    "duration_per_tool_ms",
    "errors_total",
    "tokens_total",
    "tokens_input_estimated",
    "tokens_output_estimated",
    "context_utilization",
    "prompt_avg_length",
    "prompt_total_chars",
})

# Everything else is higher-is-better by default


def _higher_is_better(metric_name: str) -> bool:
    return metric_name not in LOWER_IS_BETTER


# ── Establish baseline ────────────────────────────────────────────────

def establish_baseline(
    store: EvalStore,
    name: str,
    *,
    scenario_id: str | None = None,
    experiment_id: str | None = None,
    runs: list[RunRecord] | None = None,
) -> Baseline:
    """Establish a baseline from existing runs.

    If ``runs`` is not provided, fetches runs from the store
    matching the given filters.

    Aggregates all metrics across runs using the mean.
    """
    if runs is None:
        runs = store.list_runs(
            scenario_id=scenario_id,
            experiment_id=experiment_id,
            limit=1000,
        )

    if not runs:
        raise ValueError("No runs found to establish baseline")

    # Aggregate metrics by name
    metric_values: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        for m in run.metrics:
            metric_values[m.name].append(m.value)

    # Compute mean for each metric
    aggregated: dict[str, float] = {}
    for name_key, values in metric_values.items():
        if values:
            aggregated[name_key] = sum(values) / len(values)

    # Extract config from first run (assumes homogeneous)
    config = runs[0].config if runs else RunConfig()

    baseline = Baseline(
        baseline_id=_new_id(),
        name=name,
        created_at=_utcnow(),
        config=config,
        metrics=aggregated,
        run_count=len(runs),
        run_ids=tuple(r.run_id for r in runs),
    )

    store.save_baseline(baseline)
    logger.debug(
        "Established baseline '%s' from %d runs (%d metrics)",
        name, len(runs), len(aggregated),
    )
    return baseline


# ── Compare to baseline ──────────────────────────────────────────────

def compare_to_baseline(
    store: EvalStore,
    baseline: Baseline,
    experimental_runs: list[RunRecord],
    *,
    metric_names: list[str] | None = None,
) -> list[ComparisonResult]:
    """Compare experimental runs against a baseline.

    Returns a list of ComparisonResult — one per metric.
    If ``metric_names`` is not provided, compares all metrics
    that exist in both the baseline and experimental runs.
    """
    # Collect experimental metric values
    exp_values: dict[str, list[float]] = defaultdict(list)
    for run in experimental_runs:
        for m in run.metrics:
            exp_values[m.name].append(m.value)

    # Determine which metrics to compare
    if metric_names:
        compare_metrics = metric_names
    else:
        compare_metrics = sorted(
            set(baseline.metrics.keys()) & set(exp_values.keys())
        )

    # Load baseline run metric values for full statistical comparison
    baseline_values: dict[str, list[float]] = defaultdict(list)
    for run_id in baseline.run_ids:
        run = store.get_run(run_id)
        if run:
            for m in run.metrics:
                if m.name in compare_metrics:
                    baseline_values[m.name].append(m.value)

    # Fall back to baseline aggregated values if runs aren't available
    for name in compare_metrics:
        if name not in baseline_values and name in baseline.metrics:
            baseline_values[name] = [baseline.metrics[name]]

    # Compare each metric
    results: list[ComparisonResult] = []
    for name in compare_metrics:
        b_vals = baseline_values.get(name, [])
        e_vals = exp_values.get(name, [])
        if not b_vals or not e_vals:
            continue

        result = compare(
            name,
            b_vals,
            e_vals,
            higher_is_better=_higher_is_better(name),
        )
        results.append(result)

    logger.debug(
        "Compared %d metrics against baseline '%s'",
        len(results), baseline.name,
    )
    return results


# ── Quick check ───────────────────────────────────────────────────────

def check_regression(
    baseline: Baseline,
    run: RunRecord,
    *,
    threshold_pct: float = 10.0,
) -> list[str]:
    """Quick regression check — returns list of metric names that regressed.

    A metric is considered regressed if it's worse than
    the baseline by more than ``threshold_pct`` percent.
    """
    regressions: list[str] = []

    for m in run.metrics:
        if m.name not in baseline.metrics:
            continue

        baseline_val = baseline.metrics[m.name]
        if baseline_val == 0.0:
            continue

        pct_change = ((m.value - baseline_val) / abs(baseline_val)) * 100.0

        if _higher_is_better(m.name):
            # Higher is better — regression if value dropped
            if pct_change < -threshold_pct:
                regressions.append(m.name)
        else:
            # Lower is better — regression if value increased
            if pct_change > threshold_pct:
                regressions.append(m.name)

    return regressions
