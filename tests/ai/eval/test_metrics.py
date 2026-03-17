"""Unit tests for codeupipe.ai.eval.metrics — metric computation."""

import pytest

from codeupipe.ai.eval.metrics import (
    _METRIC_REGISTRY,
    MetricFn,
    compute_all,
    register_metric,
)
from codeupipe.ai.eval.types import (
    Metric,
    RunConfig,
    RunOutcome,
    RunRecord,
    ToolCallRecord,
    TurnSnapshot,
    _utcnow,
)


def _make_run(
    *,
    turns: int = 3,
    tools: int = 2,
    outcome: RunOutcome = RunOutcome.SUCCESS,
    model: str = "gpt-4.1",
    raw_data: dict | None = None,
) -> RunRecord:
    """Build a RunRecord for metric testing."""
    now = _utcnow()
    turn_list = tuple(
        TurnSnapshot(
            iteration=i,
            turn_type="user_prompt" if i == 0 else "follow_up",
            input_prompt="X" * 100,
            response_content="Y" * 200,
            tool_calls_count=1,
            tokens_estimated=150,
            duration_ms=300.0,
            model_used=model,
        )
        for i in range(turns)
    )
    tc_list = tuple(
        ToolCallRecord(
            iteration=i + 1,
            tool_name=f"tool_{i}",
            server_name=f"server_{i % 2}",
            arguments={"k": "v"},
            result_summary="ok",
            duration_ms=80.0,
            success=i != 1,  # tool_1 fails
        )
        for i in range(tools)
    )

    return RunRecord(
        run_id="test_run",
        config=RunConfig(model=model),
        started_at=now,
        ended_at=now,
        outcome=outcome,
        turns=turn_list,
        tool_calls=tc_list,
        raw_data=raw_data or {},
    )


def _metric_dict(metrics: list[Metric]) -> dict[str, float]:
    """Convert list of metrics to name→value dict."""
    return {m.name: m.value for m in metrics}


@pytest.mark.unit
class TestComputeAll:
    """Tests for the full compute_all pipeline."""

    def test_computes_standard_metrics(self):
        run = _make_run()
        metrics = compute_all(run)
        names = {m.name for m in metrics}

        # Core metrics exist
        assert "turns_total" in names
        assert "tool_calls_total" in names
        assert "tokens_total" in names
        assert "duration_total_ms" in names
        assert "models_unique" in names
        assert "cost_premium_requests" in names
        assert "done_naturally" in names
        assert "context_budget" in names
        assert "errors_total" in names

    def test_turns_total_correct(self):
        run = _make_run(turns=5)
        md = _metric_dict(compute_all(run))
        assert md["turns_total"] == 5.0

    def test_turns_by_type(self):
        run = _make_run(turns=4)
        md = _metric_dict(compute_all(run))
        assert md["turns_user_prompt"] == 1.0
        assert md["turns_follow_up"] == 3.0

    def test_tool_calls_count(self):
        run = _make_run(tools=3)
        md = _metric_dict(compute_all(run))
        assert md["tool_calls_total"] >= 3.0

    def test_tool_calls_unique(self):
        run = _make_run(tools=3)
        md = _metric_dict(compute_all(run))
        assert md["tool_calls_unique"] == 3.0

    def test_tool_calls_failed(self):
        run = _make_run(tools=3)
        md = _metric_dict(compute_all(run))
        assert md["tool_calls_failed"] == 1.0  # tool_1 set to fail

    def test_tool_calls_success_rate(self):
        run = _make_run(tools=4)
        md = _metric_dict(compute_all(run))
        # 1 fail out of 4 → 75%
        assert md["tool_calls_success_rate"] == 75.0

    def test_tokens_total(self):
        run = _make_run(turns=3)
        md = _metric_dict(compute_all(run))
        assert md["tokens_total"] == 450.0  # 3 turns × 150

    def test_model_metrics(self):
        run = _make_run(model="claude-sonnet-4", turns=2)
        md = _metric_dict(compute_all(run))
        assert md["models_unique"] >= 1.0
        assert md.get("model_turns_claude-sonnet-4", 0) == 2.0

    def test_outcome_success(self):
        run = _make_run(outcome=RunOutcome.SUCCESS)
        md = _metric_dict(compute_all(run))
        assert md["done_naturally"] == 1.0
        assert md["outcome_success"] == 1.0

    def test_outcome_failure(self):
        run = _make_run(outcome=RunOutcome.FAILURE)
        md = _metric_dict(compute_all(run))
        assert md["done_naturally"] == 0.0
        assert md["outcome_failure"] == 1.0

    def test_context_utilization(self):
        run = _make_run(turns=3)
        md = _metric_dict(compute_all(run))
        assert md["context_budget"] == 128_000.0
        assert md["context_utilization"] > 0

    def test_discovery_metrics_from_raw_data(self):
        run = _make_run(raw_data={
            "intent_shifts": 2,
            "discoveries_triggered": 1,
            "capabilities_adopted": 3,
            "capabilities_dropped": 1,
            "notifications_received": 4,
            "compression_events": 0,
        })
        md = _metric_dict(compute_all(run))
        assert md["intent_shifts"] == 2.0
        assert md["discoveries_triggered"] == 1.0
        assert md["capabilities_adopted"] == 3.0

    def test_prompt_metrics(self):
        run = _make_run(turns=3)
        md = _metric_dict(compute_all(run))
        assert md["prompt_avg_length"] == 100.0  # "X" * 100
        assert md["response_avg_length"] == 200.0  # "Y" * 200
        assert md["prompt_total_chars"] == 300.0

    def test_empty_turns(self):
        run = RunRecord(
            run_id="empty",
            config=RunConfig(),
            outcome=RunOutcome.UNKNOWN,
        )
        metrics = compute_all(run)
        md = _metric_dict(metrics)
        assert md["turns_total"] == 0.0


@pytest.mark.unit
class TestCustomMetrics:
    """Tests for custom metric registration."""

    def test_register_and_compute(self):
        # Register a custom metric
        def my_metric(run: RunRecord) -> list[Metric]:
            return [Metric(
                name="custom_complexity",
                value=float(len(run.turns) * len(run.tool_calls)),
                unit="score",
            )]

        register_metric("custom", my_metric)
        assert "custom" in _METRIC_REGISTRY

        run = _make_run(turns=3, tools=2)
        md = _metric_dict(compute_all(run))
        assert md["custom_complexity"] == 6.0

        # Cleanup: remove the custom metric
        del _METRIC_REGISTRY["custom"]

    def test_failing_metric_doesnt_crash(self):
        """A failing custom metric should log a warning, not crash."""
        def bad_metric(run: RunRecord) -> list[Metric]:
            raise ValueError("intentional test failure")

        register_metric("bad_metric_test", bad_metric)

        run = _make_run()
        # Should not raise
        metrics = compute_all(run)
        # Standard metrics should still be present
        names = {m.name for m in metrics}
        assert "turns_total" in names

        # Cleanup
        del _METRIC_REGISTRY["bad_metric_test"]
