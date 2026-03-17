"""Metric computation — extract named measurements from RunRecords.

Every metric answers a specific question:
  - How many prompts did it take?
  - How many loops?
  - How many tokens?
  - How many tools?
  - How many models?
  - How long?
  - How much did it cost?

Standard metrics are computed automatically from run data.
Custom metrics can be registered via ``register_metric``.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Callable

from codeupipe.ai.eval.types import Metric, RunRecord, _utcnow

logger = logging.getLogger("codeupipe.ai.eval.metrics")


# ── Metric function type ──────────────────────────────────────────────
# A metric function takes a RunRecord and returns a list of Metrics.
MetricFn = Callable[[RunRecord], list[Metric]]

# Registry of metric functions
_METRIC_REGISTRY: dict[str, MetricFn] = {}


def register_metric(name: str, fn: MetricFn) -> None:
    """Register a custom metric computation function."""
    _METRIC_REGISTRY[name] = fn
    logger.debug("Registered metric: %s", name)


def compute_all(run: RunRecord) -> list[Metric]:
    """Compute all registered metrics for a run."""
    results: list[Metric] = []
    for name, fn in _METRIC_REGISTRY.items():
        try:
            results.extend(fn(run))
        except Exception as exc:
            logger.warning("Metric %s failed: %s", name, exc)
    return results


# ── Standard metric functions ─────────────────────────────────────────

def _turns_metrics(run: RunRecord) -> list[Metric]:
    """Turn count metrics — total and by type."""
    ts = _utcnow()
    metrics = [
        Metric(name="turns_total", value=float(len(run.turns)),
               unit="count", timestamp=ts),
    ]

    type_counts: Counter[str] = Counter()
    for turn in run.turns:
        type_counts[turn.turn_type] += 1

    for turn_type, count in type_counts.items():
        metrics.append(Metric(
            name=f"turns_{turn_type}",
            value=float(count),
            unit="count",
            tags=(turn_type,),
            timestamp=ts,
        ))

    return metrics


def _tool_call_metrics(run: RunRecord) -> list[Metric]:
    """Tool usage metrics."""
    ts = _utcnow()
    total = len(run.tool_calls)
    unique_tools = len({tc.tool_name for tc in run.tool_calls})
    failed = sum(1 for tc in run.tool_calls if not tc.success)
    unique_servers = len({tc.server_name for tc in run.tool_calls if tc.server_name})

    # Tool calls from turns (in case tool_calls list isn't populated)
    turns_tool_count = sum(t.tool_calls_count for t in run.turns)
    effective_total = max(total, turns_tool_count)

    return [
        Metric(name="tool_calls_total", value=float(effective_total),
               unit="count", timestamp=ts),
        Metric(name="tool_calls_unique", value=float(unique_tools),
               unit="count", timestamp=ts),
        Metric(name="tool_calls_failed", value=float(failed),
               unit="count", timestamp=ts),
        Metric(name="tool_calls_success_rate",
               value=(effective_total - failed) / effective_total * 100.0
               if effective_total > 0 else 100.0,
               unit="percent", timestamp=ts),
        Metric(name="servers_used", value=float(unique_servers),
               unit="count", timestamp=ts),
    ]


def _token_metrics(run: RunRecord) -> list[Metric]:
    """Token consumption metrics."""
    ts = _utcnow()
    total_tokens = sum(t.tokens_estimated for t in run.turns)
    input_tokens = sum(
        len(t.input_prompt) // 4 for t in run.turns
    )
    output_tokens = sum(
        len(t.response_content or "") // 4 for t in run.turns
    )

    return [
        Metric(name="tokens_total", value=float(total_tokens),
               unit="tokens", timestamp=ts),
        Metric(name="tokens_input_estimated", value=float(input_tokens),
               unit="tokens", timestamp=ts),
        Metric(name="tokens_output_estimated", value=float(output_tokens),
               unit="tokens", timestamp=ts),
    ]


def _timing_metrics(run: RunRecord) -> list[Metric]:
    """Duration and timing metrics."""
    ts = _utcnow()
    total_ms = 0.0
    if run.started_at and run.ended_at:
        total_ms = (run.ended_at - run.started_at).total_seconds() * 1000

    turn_durations = [t.duration_ms for t in run.turns if t.duration_ms > 0]
    avg_turn_ms = sum(turn_durations) / len(turn_durations) if turn_durations else 0.0

    tool_durations = [tc.duration_ms for tc in run.tool_calls if tc.duration_ms > 0]
    avg_tool_ms = sum(tool_durations) / len(tool_durations) if tool_durations else 0.0

    return [
        Metric(name="duration_total_ms", value=total_ms,
               unit="ms", timestamp=ts),
        Metric(name="duration_per_turn_ms", value=avg_turn_ms,
               unit="ms", timestamp=ts),
        Metric(name="duration_per_tool_ms", value=avg_tool_ms,
               unit="ms", timestamp=ts),
    ]


def _model_metrics(run: RunRecord) -> list[Metric]:
    """Model usage metrics — which models, how many unique."""
    ts = _utcnow()
    models_used: Counter[str] = Counter()

    # Primary model from config
    models_used[run.config.model] += 0  # ensure it's counted

    # Models from actual turns
    for turn in run.turns:
        if turn.model_used:
            models_used[turn.model_used] += 1

    metrics = [
        Metric(name="models_unique", value=float(len(models_used)),
               unit="count", timestamp=ts),
        Metric(name="model_primary", value=1.0,
               unit="flag", tags=(run.config.model,), timestamp=ts),
    ]

    for model, count in models_used.items():
        if count > 0:
            metrics.append(Metric(
                name=f"model_turns_{model}",
                value=float(count),
                unit="count",
                tags=(model,),
                timestamp=ts,
            ))

    return metrics


def _cost_metrics(run: RunRecord) -> list[Metric]:
    """Billing and cost metrics.

    Uses MODEL_MULTIPLIERS from the SDK billing module if available,
    otherwise falls back to config model with 1.0x default.
    """
    ts = _utcnow()

    # Try to import SDK billing for accurate multipliers
    try:
        from codeupipe.ai.agent.billing import get_multiplier
    except ImportError:
        def get_multiplier(model: str) -> float:
            return 1.0

    total_requests = float(len(run.turns))
    multiplier = get_multiplier(run.config.model)
    total_premium = total_requests * multiplier

    return [
        Metric(name="cost_requests_total", value=total_requests,
               unit="requests", timestamp=ts),
        Metric(name="cost_multiplier", value=multiplier,
               unit="multiplier", timestamp=ts),
        Metric(name="cost_premium_requests", value=total_premium,
               unit="premium_requests", timestamp=ts),
    ]


def _outcome_metrics(run: RunRecord) -> list[Metric]:
    """Outcome and completion metrics."""
    ts = _utcnow()
    done_naturally = 1.0 if run.outcome == "success" else 0.0

    return [
        Metric(name="done_naturally", value=done_naturally,
               unit="flag", timestamp=ts),
        Metric(name=f"outcome_{run.outcome}", value=1.0,
               unit="flag", tags=(str(run.outcome),), timestamp=ts),
    ]


def _context_metrics(run: RunRecord) -> list[Metric]:
    """Context and budget metrics."""
    ts = _utcnow()
    budget = run.config.context_budget
    total_tokens = sum(t.tokens_estimated for t in run.turns)
    utilization = (total_tokens / budget * 100.0) if budget > 0 else 0.0

    return [
        Metric(name="context_budget", value=float(budget),
               unit="tokens", timestamp=ts),
        Metric(name="context_utilization", value=utilization,
               unit="percent", timestamp=ts),
    ]


def _discovery_metrics(run: RunRecord) -> list[Metric]:
    """Discovery-related metrics from raw data."""
    ts = _utcnow()

    # Extract from raw_data if available
    intent_shifts = float(run.raw_data.get("intent_shifts", 0))
    discoveries = float(run.raw_data.get("discoveries_triggered", 0))
    capabilities_adopted = float(run.raw_data.get("capabilities_adopted", 0))
    capabilities_dropped = float(run.raw_data.get("capabilities_dropped", 0))
    notifications_received = float(run.raw_data.get("notifications_received", 0))
    compression_events = float(run.raw_data.get("compression_events", 0))

    return [
        Metric(name="intent_shifts", value=intent_shifts,
               unit="count", timestamp=ts),
        Metric(name="discoveries_triggered", value=discoveries,
               unit="count", timestamp=ts),
        Metric(name="capabilities_adopted", value=capabilities_adopted,
               unit="count", timestamp=ts),
        Metric(name="capabilities_dropped", value=capabilities_dropped,
               unit="count", timestamp=ts),
        Metric(name="notifications_received", value=notifications_received,
               unit="count", timestamp=ts),
        Metric(name="compression_events", value=compression_events,
               unit="count", timestamp=ts),
    ]


def _error_metrics(run: RunRecord) -> list[Metric]:
    """Error tracking metrics."""
    ts = _utcnow()
    audit_errors = sum(
        1 for ae in run.audit_events
        if isinstance(ae, dict) and ae.get("error")
    )
    return [
        Metric(name="errors_total", value=float(audit_errors),
               unit="count", timestamp=ts),
    ]


def _prompt_metrics(run: RunRecord) -> list[Metric]:
    """Prompt-level metrics — lengths, complexity indicators."""
    ts = _utcnow()
    if not run.turns:
        return []

    prompt_lengths = [len(t.input_prompt) for t in run.turns]
    response_lengths = [
        len(t.response_content) for t in run.turns if t.response_content
    ]
    avg_prompt = sum(prompt_lengths) / len(prompt_lengths)
    avg_response = sum(response_lengths) / len(response_lengths) if response_lengths else 0.0

    return [
        Metric(name="prompt_avg_length", value=avg_prompt,
               unit="chars", timestamp=ts),
        Metric(name="response_avg_length", value=avg_response,
               unit="chars", timestamp=ts),
        Metric(name="prompt_total_chars", value=float(sum(prompt_lengths)),
               unit="chars", timestamp=ts),
        Metric(name="response_total_chars", value=float(sum(response_lengths)),
               unit="chars", timestamp=ts),
    ]


# ── Register all standard metrics ────────────────────────────────────

_STANDARD_METRICS: dict[str, MetricFn] = {
    "turns": _turns_metrics,
    "tool_calls": _tool_call_metrics,
    "tokens": _token_metrics,
    "timing": _timing_metrics,
    "models": _model_metrics,
    "cost": _cost_metrics,
    "outcome": _outcome_metrics,
    "context": _context_metrics,
    "discovery": _discovery_metrics,
    "errors": _error_metrics,
    "prompts": _prompt_metrics,
}


def register_standard_metrics() -> None:
    """Register all built-in metric functions."""
    for name, fn in _STANDARD_METRICS.items():
        register_metric(name, fn)


# Auto-register on import
register_standard_metrics()


# ── Derived metrics framework ─────────────────────────────────────────


def _find_metric(run: RunRecord, name: str) -> float | None:
    """Find a metric value by name in a RunRecord."""
    for m in run.metrics:
        if m.name == name:
            return m.value
    return None


def ratio_metric(
    name: str,
    numerator: str,
    denominator: str,
    *,
    unit: str = "ratio",
    default: float = 0.0,
) -> MetricFn:
    """Create a derived metric that computes numerator / denominator.

    Usage:
        register_metric("cost_per_turn",
            ratio_metric("cost_per_turn",
                         "cost_premium_requests", "turns_total"))
    """
    def _compute(run: RunRecord) -> list[Metric]:
        num = _find_metric(run, numerator)
        den = _find_metric(run, denominator)
        if num is None or den is None or den == 0.0:
            value = default
        else:
            value = num / den
        return [Metric(name=name, value=value, unit=unit, timestamp=_utcnow())]
    return _compute


def difference_metric(
    name: str,
    metric_a: str,
    metric_b: str,
    *,
    unit: str = "delta",
) -> MetricFn:
    """Create a derived metric that computes metric_a - metric_b."""
    def _compute(run: RunRecord) -> list[Metric]:
        a = _find_metric(run, metric_a)
        b = _find_metric(run, metric_b)
        if a is None or b is None:
            return []
        return [Metric(name=name, value=a - b, unit=unit, timestamp=_utcnow())]
    return _compute


def product_metric(
    name: str,
    metric_a: str,
    metric_b: str,
    *,
    unit: str = "product",
) -> MetricFn:
    """Create a derived metric that computes metric_a × metric_b."""
    def _compute(run: RunRecord) -> list[Metric]:
        a = _find_metric(run, metric_a)
        b = _find_metric(run, metric_b)
        if a is None or b is None:
            return []
        return [Metric(name=name, value=a * b, unit=unit, timestamp=_utcnow())]
    return _compute


def threshold_metric(
    name: str,
    source: str,
    *,
    threshold: float,
    above: bool = True,
    unit: str = "flag",
) -> MetricFn:
    """Create a derived metric that's 1.0 if source is above/below threshold.

    Usage:
        register_metric("over_budget",
            threshold_metric("over_budget",
                            "context_utilization", threshold=100.0))
    """
    def _compute(run: RunRecord) -> list[Metric]:
        val = _find_metric(run, source)
        if val is None:
            return []
        if above:
            flag = 1.0 if val > threshold else 0.0
        else:
            flag = 1.0 if val < threshold else 0.0
        return [Metric(name=name, value=flag, unit=unit, timestamp=_utcnow())]
    return _compute


def composite_metric(
    name: str,
    components: dict[str, float],
    *,
    unit: str = "score",
) -> MetricFn:
    """Create a weighted composite metric from multiple sources.

    ``components`` maps metric_name → weight.  Computes the
    weighted average of available component metrics.

    Usage:
        register_metric("efficiency_score",
            composite_metric("efficiency_score", {
                "done_naturally": 0.4,
                "tool_calls_success_rate": 0.3,
                "context_utilization": -0.3,  # lower is better
            }))
    """
    def _compute(run: RunRecord) -> list[Metric]:
        total_weight = 0.0
        weighted_sum = 0.0
        for metric_name, weight in components.items():
            val = _find_metric(run, metric_name)
            if val is not None:
                weighted_sum += val * weight
                total_weight += abs(weight)
        if total_weight == 0.0:
            return []
        value = weighted_sum / total_weight
        return [Metric(name=name, value=value, unit=unit, timestamp=_utcnow())]
    return _compute


# ── Register standard derived metrics ─────────────────────────────────

_DERIVED_METRICS: dict[str, MetricFn] = {
    "cost_per_turn": ratio_metric(
        "cost_per_turn", "cost_premium_requests", "turns_total",
        unit="premium_requests/turn",
    ),
    "tokens_per_turn": ratio_metric(
        "tokens_per_turn", "tokens_total", "turns_total",
        unit="tokens/turn",
    ),
    "tool_calls_per_turn": ratio_metric(
        "tool_calls_per_turn", "tool_calls_total", "turns_total",
        unit="calls/turn",
    ),
}


def register_derived_metrics() -> None:
    """Register all built-in derived metric functions."""
    for name, fn in _DERIVED_METRICS.items():
        register_metric(name, fn)


# Auto-register derived metrics
register_derived_metrics()
