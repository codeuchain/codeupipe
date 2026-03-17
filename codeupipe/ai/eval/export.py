"""Export — Get eval data out for external analysis.

Supports multiple output formats:
  - CSV — for spreadsheets and pandas
  - JSONL — for streaming pipelines and jq
  - Summary dict — for programmatic consumption

The philosophy: raw data is priceless, but only if you can
get it *out* of the database and into the tools that need it.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import RunRecord

logger = logging.getLogger("codeupipe.ai.eval.export")


# ── Run export ────────────────────────────────────────────────────────


def runs_to_csv(
    runs: list[RunRecord],
    *,
    metric_names: list[str] | None = None,
) -> str:
    """Export runs to CSV string.

    Each row is one run.  Metric values are flattened into columns.
    If ``metric_names`` is provided, only those metrics become columns.
    Otherwise, all metrics from all runs are included.

    Returns the CSV as a string.
    """
    if not runs:
        return ""

    # Collect all metric names
    if metric_names is None:
        all_names: set[str] = set()
        for run in runs:
            for m in run.metrics:
                all_names.add(m.name)
        metric_names = sorted(all_names)

    # Build header
    base_cols = [
        "run_id", "session_id", "scenario_id", "experiment_id",
        "model", "outcome", "started_at", "ended_at",
        "turns_count", "tool_calls_count",
    ]
    header = base_cols + metric_names

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)

    for run in runs:
        # Build metric lookup
        metric_vals: dict[str, float] = {}
        for m in run.metrics:
            metric_vals[m.name] = m.value

        row = [
            run.run_id,
            run.session_id,
            run.scenario_id or "",
            run.experiment_id or "",
            run.config.model,
            str(run.outcome),
            run.started_at.isoformat(),
            run.ended_at.isoformat() if run.ended_at else "",
            len(run.turns),
            len(run.tool_calls),
        ]
        for name in metric_names:
            row.append(metric_vals.get(name, ""))

        writer.writerow(row)

    return output.getvalue()


def runs_to_jsonl(runs: list[RunRecord]) -> str:
    """Export runs to JSONL string (one JSON object per line).

    Each line is a complete RunRecord serialized as JSON.
    Ideal for streaming to external pipelines or ``jq``.
    """
    lines: list[str] = []
    for run in runs:
        lines.append(json.dumps(run.to_dict(), default=str))
    return "\n".join(lines) + "\n" if lines else ""


def run_to_summary(run: RunRecord) -> dict:
    """Convert a RunRecord to a flat summary dict.

    Metrics are flattened into top-level keys prefixed with ``m_``.
    Config values are prefixed with ``c_``.
    Suitable for pandas DataFrames: ``pd.DataFrame([run_to_summary(r)])``.
    """
    summary: dict = {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "scenario_id": run.scenario_id,
        "experiment_id": run.experiment_id,
        "outcome": str(run.outcome),
        "started_at": run.started_at.isoformat(),
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "turns_count": len(run.turns),
        "tool_calls_count": len(run.tool_calls),
        "audit_events_count": len(run.audit_events),
        # Config
        "c_model": run.config.model,
        "c_max_iterations": run.config.max_iterations,
        "c_context_budget": run.config.context_budget,
        "c_discovery_top_k": run.config.discovery_top_k,
        "c_similarity_threshold": run.config.similarity_threshold,
        "c_embedding_model": run.config.embedding_model,
    }

    # Flatten metrics
    for m in run.metrics:
        summary[f"m_{m.name}"] = m.value

    # Duration
    if run.started_at and run.ended_at:
        summary["duration_s"] = (
            run.ended_at - run.started_at
        ).total_seconds()

    return summary


def runs_to_summary_dicts(runs: list[RunRecord]) -> list[dict]:
    """Convert a list of RunRecords to flat summary dicts.

    Ready for ``pd.DataFrame(runs_to_summary_dicts(runs))``.
    """
    return [run_to_summary(r) for r in runs]


# ── File export helpers ───────────────────────────────────────────────


def save_csv(
    runs: list[RunRecord],
    path: str | Path,
    *,
    metric_names: list[str] | None = None,
) -> None:
    """Export runs to a CSV file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = runs_to_csv(runs, metric_names=metric_names)
    path.write_text(content)
    logger.debug("Exported %d runs to CSV: %s", len(runs), path)


def save_jsonl(
    runs: list[RunRecord],
    path: str | Path,
) -> None:
    """Export runs to a JSONL file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = runs_to_jsonl(runs)
    path.write_text(content)
    logger.debug("Exported %d runs to JSONL: %s", len(runs), path)


# ── Raw event export ─────────────────────────────────────────────────


def raw_events_to_jsonl(
    store: EvalStore,
    path: str | Path,
    *,
    run_id: str = "",
    event_type: str = "",
    limit: int = 10_000,
) -> int:
    """Export raw events from the store to a JSONL file.

    Returns the number of events exported.
    """
    events = store.get_raw_events(
        run_id=run_id, event_type=event_type, limit=limit,
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w") as f:
        for event in events:
            f.write(json.dumps(event.to_dict(), default=str) + "\n")

    logger.debug("Exported %d raw events to %s", len(events), path)
    return len(events)


# ── Metric export ────────────────────────────────────────────────────


def metrics_to_csv(
    runs: list[RunRecord],
    path: str | Path,
) -> None:
    """Export all metrics from runs to a long-format CSV.

    Long format: one row per (run_id, metric_name, value).
    Easier for pivot tables and groupby operations.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "run_id", "scenario_id", "model", "outcome",
            "metric_name", "value", "unit", "tags",
        ])
        for run in runs:
            for m in run.metrics:
                writer.writerow([
                    run.run_id,
                    run.scenario_id or "",
                    run.config.model,
                    str(run.outcome),
                    m.name,
                    m.value,
                    m.unit,
                    ";".join(m.tags),
                ])

    logger.debug("Exported metrics from %d runs to %s", len(runs), path)
