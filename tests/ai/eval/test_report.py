"""Unit tests for codeupipe.ai.eval.report — markdown report generation."""

import pytest

from codeupipe.ai.eval.report import (
    aggregate_report_md,
    baseline_report_md,
    comparison_report_md,
    run_report_md,
    run_summary,
    save_report,
)
from codeupipe.ai.eval.stats import ComparisonResult, DescriptiveStats, compare
from codeupipe.ai.eval.types import (
    Baseline,
    Metric,
    RunConfig,
    RunOutcome,
    RunRecord,
    ToolCallRecord,
    TurnSnapshot,
    _utcnow,
)


def _make_run(
    run_id: str = "run_1",
    *,
    turns: int = 3,
    outcome: RunOutcome = RunOutcome.SUCCESS,
) -> RunRecord:
    now = _utcnow()
    turn_list = tuple(
        TurnSnapshot(
            iteration=i,
            turn_type="user_prompt" if i == 0 else "follow_up",
            input_prompt=f"test prompt {i}",
            response_content=f"response {i}",
            tool_calls_count=1,
            tokens_estimated=100,
            duration_ms=300.0,
            model_used="gpt-4.1",
        )
        for i in range(turns)
    )
    return RunRecord(
        run_id=run_id,
        session_id="sess_1",
        config=RunConfig(model="gpt-4.1"),
        started_at=now,
        ended_at=now,
        outcome=outcome,
        turns=turn_list,
        tool_calls=(
            ToolCallRecord(
                iteration=1,
                tool_name="echo",
                server_name="test-server",
                duration_ms=50.0,
            ),
        ),
        metrics=(
            Metric(name="turns_total", value=float(turns), unit="count"),
            Metric(name="tokens_total", value=float(turns * 100), unit="tokens"),
            Metric(name="cost_premium_requests", value=2.0, unit="premium_requests"),
        ),
    )


@pytest.mark.unit
class TestRunSummary:
    def test_contains_key_info(self):
        run = _make_run()
        summary = run_summary(run)

        assert "run_1" in summary
        assert "success" in summary
        assert "gpt-4.1" in summary

    def test_metrics_shown(self):
        run = _make_run()
        summary = run_summary(run)
        assert "turns_total" in summary


@pytest.mark.unit
class TestRunReportMd:
    def test_markdown_structure(self):
        run = _make_run()
        md = run_report_md(run)

        assert "# Evaluation Run Report" in md
        assert "## Metrics" in md
        assert "## Turns" in md
        assert "## Tool Calls" in md
        assert "## Configuration" in md

    def test_metrics_table(self):
        run = _make_run()
        md = run_report_md(run)

        assert "| turns_total" in md
        assert "| tokens_total" in md

    def test_turns_table(self):
        run = _make_run(turns=2)
        md = run_report_md(run)

        assert "user_prompt" in md
        assert "follow_up" in md

    def test_tool_calls_table(self):
        run = _make_run()
        md = run_report_md(run)

        assert "echo" in md
        assert "test-server" in md

    def test_scenario_shown_if_present(self):
        run = RunRecord(
            run_id="r1",
            scenario_id="sc_42",
            config=RunConfig(),
        )
        md = run_report_md(run)
        assert "sc_42" in md


@pytest.mark.unit
class TestComparisonReportMd:
    def test_basic_comparison(self):
        comparisons = [
            compare("turns_total", [3, 4, 5], [2, 2, 3], higher_is_better=False),
            compare("cost", [3, 4], [1, 2], higher_is_better=False),
        ]
        md = comparison_report_md(comparisons)

        assert "# Comparison Report" in md
        assert "turns_total" in md
        assert "cost" in md
        assert "Improved" in md

    def test_custom_labels(self):
        comparisons = [
            compare("turns_total", [3, 4], [2, 3], higher_is_better=False),
        ]
        md = comparison_report_md(
            comparisons,
            title="Model A vs B",
            baseline_label="GPT-4.1",
            experimental_label="Claude Sonnet 4",
        )

        assert "Model A vs B" in md
        assert "GPT-4.1" in md
        assert "Claude Sonnet 4" in md

    def test_notable_changes(self):
        # Large improvement (>10%)
        comparisons = [
            compare("turns_total", [10, 10, 10], [2, 2, 2], higher_is_better=False),
        ]
        md = comparison_report_md(comparisons)
        assert "Notable Changes" in md


@pytest.mark.unit
class TestBaselineReportMd:
    def test_basic(self):
        baseline = Baseline(
            name="default-v1",
            config=RunConfig(model="gpt-4.1"),
            metrics={"turns_total": 3.5, "cost_premium_requests": 2.0},
            run_count=10,
        )
        md = baseline_report_md(baseline)

        assert "default-v1" in md
        assert "gpt-4.1" in md
        assert "10" in md
        assert "turns_total" in md
        assert "3.5" in md


@pytest.mark.unit
class TestAggregateReportMd:
    def test_basic(self):
        runs = [
            _make_run("r1", turns=3),
            _make_run("r2", turns=5),
            _make_run("r3", turns=4, outcome=RunOutcome.FAILURE),
        ]
        md = aggregate_report_md(runs)

        assert "# Aggregate Run Report" in md
        assert "Total runs**: 3" in md
        assert "## Metrics" in md
        assert "turns_total" in md

    def test_empty(self):
        md = aggregate_report_md([])
        assert "Total runs**: 0" in md


@pytest.mark.unit
class TestSaveReport:
    def test_save_to_file(self, tmp_path):
        content = "# Test Report\n\nSome content."
        path = tmp_path / "reports" / "test.md"
        save_report(content, path)

        assert path.exists()
        assert path.read_text() == content

    def test_creates_directory(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "report.md"
        save_report("content", path)
        assert path.exists()
