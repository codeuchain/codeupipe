"""Report generation — Markdown and terminal output for eval results.

Produces human-readable reports from RunRecords, ExperimentResults,
baselines, comparisons, and trends.

Iteration 3 additions:
  - experiment_report_md()   — Full experiment summary with per-config stats
  - trend_report_md()        — Metric trends over time
  - regression_report_md()   — Regression alert report from comparator
  - dashboard_report_md()    — Health dashboard in Markdown
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from codeupipe.ai.eval.stats import ComparisonResult, DescriptiveStats, describe
from codeupipe.ai.eval.types import Baseline, Metric, RunRecord

logger = logging.getLogger("codeupipe.ai.eval.report")


# ── Single run report ─────────────────────────────────────────────────

def run_summary(run: RunRecord) -> str:
    """Generate a concise text summary of a single run."""
    lines = [
        f"Run: {run.run_id}",
        f"  Outcome:    {run.outcome}",
        f"  Turns:      {len(run.turns)}",
        f"  Tool calls: {len(run.tool_calls)}",
        f"  Model:      {run.config.model}",
    ]

    if run.started_at and run.ended_at:
        duration = (run.ended_at - run.started_at).total_seconds()
        lines.append(f"  Duration:   {duration:.1f}s")

    # Key metrics
    key_metrics = [
        "turns_total", "tool_calls_total", "tokens_total",
        "cost_premium_requests", "duration_total_ms",
        "score_weighted_avg", "score_pass_rate",
    ]
    for m in run.metrics:
        if m.name in key_metrics:
            lines.append(f"  {m.name}: {m.value:.2f} {m.unit}")

    return "\n".join(lines)


# ── Markdown report for a run ─────────────────────────────────────────

def run_report_md(run: RunRecord) -> str:
    """Generate a detailed Markdown report for a single run."""
    lines = [
        f"# Evaluation Run Report",
        f"",
        f"**Run ID**: `{run.run_id}`  ",
        f"**Session**: `{run.session_id}`  ",
        f"**Outcome**: {run.outcome}  ",
        f"**Model**: {run.config.model}  ",
    ]

    if run.started_at and run.ended_at:
        duration = (run.ended_at - run.started_at).total_seconds()
        lines.append(f"**Duration**: {duration:.1f}s  ")

    if run.scenario_id:
        lines.append(f"**Scenario**: `{run.scenario_id}`  ")

    lines.append("")

    # Metrics table
    if run.metrics:
        lines.extend([
            "## Metrics",
            "",
            "| Metric | Value | Unit |",
            "|--------|-------|------|",
        ])
        for m in sorted(run.metrics, key=lambda x: x.name):
            lines.append(f"| {m.name} | {m.value:.4f} | {m.unit} |")
        lines.append("")

    # Turn details
    if run.turns:
        lines.extend([
            "## Turns",
            "",
            "| # | Type | Prompt (first 60) | Tools | Tokens | Duration |",
            "|---|------|-------------------|-------|--------|----------|",
        ])
        for t in run.turns:
            prompt_preview = (t.input_prompt[:60] + "...") if len(t.input_prompt) > 60 else t.input_prompt
            prompt_preview = prompt_preview.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {t.iteration} | {t.turn_type} | {prompt_preview} "
                f"| {t.tool_calls_count} | {t.tokens_estimated} | {t.duration_ms:.0f}ms |"
            )
        lines.append("")

    # Tool calls
    if run.tool_calls:
        lines.extend([
            "## Tool Calls",
            "",
            "| Iter | Tool | Server | Success | Duration |",
            "|------|------|--------|---------|----------|",
        ])
        for tc in run.tool_calls:
            status = "yes" if tc.success else "FAILED"
            lines.append(
                f"| {tc.iteration} | {tc.tool_name} | {tc.server_name} "
                f"| {status} | {tc.duration_ms:.0f}ms |"
            )
        lines.append("")

    # Config
    lines.extend([
        "## Configuration",
        "",
        "```json",
        _safe_json(run.config.to_dict()),
        "```",
        "",
    ])

    return "\n".join(lines)


# ── Comparison report ─────────────────────────────────────────────────

def comparison_report_md(
    comparisons: list[ComparisonResult],
    *,
    title: str = "Comparison Report",
    baseline_label: str = "Baseline",
    experimental_label: str = "Experimental",
) -> str:
    """Generate a Markdown comparison report."""
    lines = [
        f"# {title}",
        "",
        f"**Baseline**: {baseline_label}  ",
        f"**Experimental**: {experimental_label}  ",
        f"**Metrics compared**: {len(comparisons)}  ",
        "",
        "## Results",
        "",
        "| Metric | Baseline (mean) | Experimental (mean) | Change | Effect | Improved? |",
        "|--------|----------------|--------------------:|-------:|-------:|-----------|",
    ]

    for c in sorted(comparisons, key=lambda x: abs(x.percent_change), reverse=True):
        direction = "higher better" if c.higher_is_better else "lower better"
        improved = "yes" if c.improved else "**NO**"
        lines.append(
            f"| {c.metric_name} | {c.baseline_stats.mean:.2f} "
            f"| {c.experimental_stats.mean:.2f} "
            f"| {c.percent_change:+.1f}% "
            f"| {c.effect_label} (d={c.cohens_d:.2f}) "
            f"| {improved} |"
        )

    lines.append("")

    # Summary
    improved_count = sum(1 for c in comparisons if c.improved)
    regressed_count = sum(1 for c in comparisons if not c.improved)
    lines.extend([
        "## Summary",
        "",
        f"- **Improved**: {improved_count}/{len(comparisons)} metrics",
        f"- **Regressed**: {regressed_count}/{len(comparisons)} metrics",
        "",
    ])

    # Highlight notable changes
    notable = [c for c in comparisons if abs(c.percent_change) > 10]
    if notable:
        lines.extend([
            "## Notable Changes (>10%)",
            "",
        ])
        for c in sorted(notable, key=lambda x: abs(x.percent_change), reverse=True):
            emoji = "+" if c.improved else "-"
            lines.append(
                f"- [{emoji}] **{c.metric_name}**: {c.percent_change:+.1f}% "
                f"({c.baseline_stats.mean:.2f} → {c.experimental_stats.mean:.2f})"
            )
        lines.append("")

    return "\n".join(lines)


# ── Baseline report ───────────────────────────────────────────────────

def baseline_report_md(baseline: Baseline) -> str:
    """Generate a Markdown report for a baseline."""
    lines = [
        f"# Baseline: {baseline.name}",
        "",
        f"**ID**: `{baseline.baseline_id}`  ",
        f"**Created**: {baseline.created_at.isoformat()}  ",
        f"**Runs**: {baseline.run_count}  ",
        f"**Model**: {baseline.config.model}  ",
        "",
        "## Aggregated Metrics (mean across runs)",
        "",
        "| Metric | Value |",
        "|--------|------:|",
    ]

    for name in sorted(baseline.metrics.keys()):
        value = baseline.metrics[name]
        lines.append(f"| {name} | {value:.4f} |")

    lines.append("")
    return "\n".join(lines)


# ── Multi-run aggregate report ────────────────────────────────────────

def aggregate_report_md(
    runs: list[RunRecord],
    *,
    title: str = "Aggregate Run Report",
) -> str:
    """Generate a statistical summary across multiple runs."""
    lines = [
        f"# {title}",
        "",
        f"**Total runs**: {len(runs)}  ",
    ]

    if runs:
        outcomes = {}
        for run in runs:
            outcomes[str(run.outcome)] = outcomes.get(str(run.outcome), 0) + 1
        for outcome, count in sorted(outcomes.items()):
            lines.append(f"**{outcome}**: {count}  ")
    lines.append("")

    # Aggregate metrics
    from collections import defaultdict
    metric_values: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        for m in run.metrics:
            metric_values[m.name].append(m.value)

    if metric_values:
        lines.extend([
            "## Metrics",
            "",
            "| Metric | Mean | Median | StdDev | Min | Max | P95 |",
            "|--------|-----:|-------:|-------:|----:|----:|----:|",
        ])
        for name in sorted(metric_values.keys()):
            stats = describe(metric_values[name])
            lines.append(
                f"| {name} | {stats.mean:.2f} | {stats.median:.2f} "
                f"| {stats.stddev:.2f} | {stats.min:.2f} "
                f"| {stats.max:.2f} | {stats.p95:.2f} |"
            )
        lines.append("")

    return "\n".join(lines)


# ── Save report ───────────────────────────────────────────────────────

def save_report(content: str, path: str | Path) -> None:
    """Write a report to a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    logger.debug("Report saved to %s", path)


# ── Helpers ───────────────────────────────────────────────────────────

def _safe_json(data: dict) -> str:
    """JSON serialize with fallback for non-serializable types."""
    import json
    return json.dumps(data, indent=2, default=str)


# ── Experiment report ─────────────────────────────────────────────────

def experiment_report_md(
    experiment_result: object,
) -> str:
    """Generate a Markdown report for a completed experiment.

    Args:
        experiment_result: An ExperimentResult (imported lazily to
            avoid circular imports).

    Returns:
        Markdown string with per-config stats, comparisons, and scores.
    """
    er = experiment_result  # type: ignore[assignment]
    exp = er.experiment

    lines = [
        f"# Experiment Report: {exp.name}",
        "",
        f"**ID**: `{exp.experiment_id}`  ",
        f"**Status**: {exp.status}  ",
        f"**Created**: {exp.created_at.isoformat()}  ",
        f"**Total runs**: {er.total_runs}  ",
        f"**Configs**: {len(er.config_labels())}  ",
        f"**Scenarios**: {len(exp.scenario_ids)}  ",
    ]
    if exp.description:
        lines.append(f"**Description**: {exp.description}  ")
    lines.append("")

    # Per-config overview
    lines.extend([
        "## Config Overview",
        "",
        "| Config | Runs | Model |",
        "|--------|-----:|-------|",
    ])
    for label in er.config_labels():
        runs = er.runs_by_config.get(label, [])
        model = runs[0].config.model if runs else "?"
        lines.append(f"| {label} | {len(runs)} | {model} |")
    lines.append("")

    # Metric comparison across configs
    # Collect all metric names
    from collections import defaultdict
    all_metric_names: set[str] = set()
    for runs in er.runs_by_config.values():
        for run in runs:
            for m in run.metrics:
                all_metric_names.add(m.name)

    key_metrics = [
        "turns_total", "tool_calls_total", "tokens_total",
        "cost_premium_requests", "duration_total_ms",
        "done_naturally", "tool_calls_success_rate",
    ]
    display_metrics = [m for m in key_metrics if m in all_metric_names]

    if display_metrics:
        config_labels = er.config_labels()
        header = "| Metric | " + " | ".join(config_labels) + " |"
        separator = "|--------|" + "|".join("-:" * len(config_labels)) + "|"

        lines.extend([
            "## Key Metrics (mean across runs)",
            "",
            header,
            separator,
        ])

        for metric_name in display_metrics:
            values_str = []
            for label in config_labels:
                summary = er.metric_summary(metric_name)
                config_stats = summary.get(label, {})
                mean_val = config_stats.get("mean", 0.0)
                values_str.append(f"{mean_val:.2f}")
            lines.append(f"| {metric_name} | " + " | ".join(values_str) + " |")
        lines.append("")

    # Comparisons
    if er.comparisons:
        lines.extend([
            "## Comparisons vs Baseline",
            "",
            "| Metric | Change | Effect | Improved? |",
            "|--------|-------:|-------:|-----------|",
        ])
        for c in sorted(er.comparisons, key=lambda x: abs(x.percent_change), reverse=True):
            improved = "yes" if c.improved else "**NO**"
            lines.append(
                f"| {c.metric_name} | {c.percent_change:+.1f}% "
                f"| {c.effect_label} | {improved} |"
            )
        lines.append("")

    # Scores
    if er.scores:
        lines.extend([
            "## Deterministic Scores",
            "",
            "| Run | Weighted Avg | Pass Rate |",
            "|-----|-------------:|-----------:|",
        ])
        for s in er.scores:
            lines.append(
                f"| `{s.run_id[:12]}` | {s.weighted_average:.2f} "
                f"| {s.pass_rate:.0f}% |"
            )
        lines.append("")

    return "\n".join(lines)


# ── Trend report ──────────────────────────────────────────────────────

def trend_report_md(
    runs: list[RunRecord],
    *,
    metric_names: list[str] | None = None,
    title: str = "Metric Trend Report",
) -> str:
    """Generate a Markdown trend report showing metric values over time.

    Args:
        runs: Runs ordered by time (oldest first).
        metric_names: Metrics to include (None = auto-detect key metrics).
        title: Report title.

    Returns:
        Markdown with per-metric trend tables and direction indicators.
    """
    from codeupipe.ai.eval.stats import analyze_trend

    lines = [
        f"# {title}",
        "",
        f"**Runs analyzed**: {len(runs)}  ",
    ]
    if runs:
        lines.append(f"**Period**: {_fmt_dt(runs[0].started_at)} → {_fmt_dt(runs[-1].started_at)}  ")
    lines.append("")

    # Collect metric values in order
    from collections import defaultdict
    metric_series: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        for m in run.metrics:
            metric_series[m.name].append(m.value)

    if metric_names is None:
        metric_names = [
            n for n in [
                "turns_total", "tool_calls_total", "tokens_total",
                "cost_premium_requests", "duration_total_ms",
                "done_naturally", "tool_calls_success_rate",
                "context_utilization",
            ]
            if n in metric_series
        ]

    if not metric_names:
        lines.append("*No metrics found for trend analysis.*")
        return "\n".join(lines)

    lines.extend([
        "## Trend Summary",
        "",
        "| Metric | Direction | Slope | R² | First | Last | Change |",
        "|--------|-----------|------:|---:|------:|-----:|-------:|",
    ])

    for name in metric_names:
        values = metric_series.get(name, [])
        if len(values) < 3:
            lines.append(f"| {name} | insufficient data | — | — | — | — | — |")
            continue

        trend = analyze_trend(values)
        first_val = values[0]
        last_val = values[-1]
        change = last_val - first_val

        direction = "→ stable"
        if trend.direction == "increasing":
            direction = "↑ increasing"
        elif trend.direction == "decreasing":
            direction = "↓ decreasing"

        lines.append(
            f"| {name} | {direction} "
            f"| {trend.slope:.4f} | {trend.r_squared:.3f} "
            f"| {first_val:.2f} | {last_val:.2f} "
            f"| {change:+.2f} |"
        )

    lines.append("")
    return "\n".join(lines)


# ── Regression report ─────────────────────────────────────────────────

def regression_report_md(
    alerts: list[object],
    *,
    title: str = "Regression Report",
) -> str:
    """Generate a Markdown regression alert report.

    Args:
        alerts: List of RegressionAlert objects from comparator.
        title: Report title.

    Returns:
        Markdown with severity-colored alert table.
    """
    lines = [
        f"# {title}",
        "",
        f"**Total alerts**: {len(alerts)}  ",
    ]

    if not alerts:
        lines.append("")
        lines.append("No regressions detected.")
        return "\n".join(lines)

    critical = [a for a in alerts if a.severity == "critical"]  # type: ignore[attr-defined]
    warning = [a for a in alerts if a.severity == "warning"]  # type: ignore[attr-defined]

    lines.append(f"**Critical**: {len(critical)}  ")
    lines.append(f"**Warning**: {len(warning)}  ")
    lines.append("")

    lines.extend([
        "## Alerts",
        "",
        "| Severity | Metric | Baseline | Current | Change |",
        "|----------|--------|:--------:|:-------:|-------:|",
    ])

    for a in alerts:
        sev = f"**{a.severity.upper()}**" if a.severity == "critical" else a.severity  # type: ignore[attr-defined]
        lines.append(
            f"| {sev} | {a.metric} "  # type: ignore[attr-defined]
            f"| {a.baseline_mean:.2f} "  # type: ignore[attr-defined]
            f"| {a.current_mean:.2f} "  # type: ignore[attr-defined]
            f"| {a.pct_change:+.1f}% |"  # type: ignore[attr-defined]
        )

    lines.append("")
    return "\n".join(lines)


# ── Dashboard report ─────────────────────────────────────────────────

def dashboard_report_md(
    dashboard: object,
    *,
    title: str = "Health Dashboard",
) -> str:
    """Generate a Markdown health dashboard report.

    Args:
        dashboard: A HealthDashboard object from analytics.
        title: Report title.

    Returns:
        Markdown with link profiles, sessions, anomalies, tools.
    """
    d = dashboard  # type: ignore[assignment]
    lines = [
        f"# {title}",
        "",
        f"**Total runs**: {d.total_runs}  ",
        f"**Total errors**: {d.total_errors}  ",
        f"**Error rate**: {d.overall_error_rate:.1f}%  ",
        "",
    ]

    # Link profiles
    if d.link_profiles:
        lines.extend([
            "## Link Performance",
            "",
            "| Link | Calls | Errors | Error% | Avg ms | Total ms | % Time |",
            "|------|------:|-------:|-------:|-------:|---------:|-------:|",
        ])
        for lp in d.link_profiles:
            lines.append(
                f"| {lp.link_name} | {lp.invocation_count} "
                f"| {lp.error_count} | {lp.error_rate:.1f}% "
                f"| {lp.timing.mean:.0f} | {lp.total_time_ms:.0f} "
                f"| {lp.percent_of_total:.1f}% |"
            )
        lines.append("")

    # Session summaries
    if d.session_summaries:
        lines.extend([
            "## Sessions",
            "",
            "| Session | Events | Iterations | Duration | Errors | Bottleneck |",
            "|---------|-------:|-----------:|---------:|-------:|------------|",
        ])
        for ss in d.session_summaries[:10]:
            lines.append(
                f"| `{ss.session_id[:12]}` | {ss.total_events} "
                f"| {ss.total_iterations} | {ss.total_duration_ms:.0f}ms "
                f"| {ss.total_errors} | {ss.bottleneck_link} |"
            )
        lines.append("")

    # Timing anomalies
    if d.timing_anomalies:
        lines.extend([
            "## Timing Anomalies",
            "",
            "| Link | Duration | Z-Score | Iteration |",
            "|------|---------:|--------:|----------:|",
        ])
        for ta in d.timing_anomalies[:10]:
            lines.append(
                f"| {ta.link_name} | {ta.duration_ms:.0f}ms "
                f"| {ta.z_score:.2f} | {ta.iteration} |"
            )
        lines.append("")

    # Turn distribution
    if d.turn_distribution:
        lines.extend([
            "## Turn Distribution",
            "",
            "| Turn Type | Count |",
            "|-----------|------:|",
        ])
        for tt, count in sorted(d.turn_distribution.items(), key=lambda x: -x[1]):
            lines.append(f"| {tt} | {count} |")
        lines.append("")

    # Tool profiles
    if d.tool_profiles:
        lines.extend([
            "## Tool Usage",
            "",
            "| Tool | Calls | Success% | Avg ms |",
            "|------|------:|---------:|-------:|",
        ])
        for tp in d.tool_profiles:
            lines.append(
                f"| {tp.tool_name} | {tp.call_count} "
                f"| {tp.success_rate:.0f}% | {tp.timing.mean:.0f} |"
            )
        lines.append("")

    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────

def _fmt_dt(dt: datetime | None) -> str:
    """Format a datetime for display."""
    if dt is None:
        return "?"
    return dt.strftime("%Y-%m-%d %H:%M")
