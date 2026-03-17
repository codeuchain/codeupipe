"""Unit tests for codeupipe.ai.eval.export — data export capabilities."""

import csv
import io
import json

import pytest

from codeupipe.ai.eval.export import (
    metrics_to_csv,
    raw_events_to_jsonl,
    run_to_summary,
    runs_to_csv,
    runs_to_jsonl,
    runs_to_summary_dicts,
    save_csv,
    save_jsonl,
)
from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    Metric,
    RawEvent,
    RunConfig,
    RunOutcome,
    RunRecord,
    TurnSnapshot,
    ToolCallRecord,
    _utcnow,
)


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_run(
    run_id: str = "r1",
    model: str = "gpt-4.1",
    outcome: RunOutcome = RunOutcome.SUCCESS,
    n_turns: int = 2,
    n_tools: int = 1,
) -> RunRecord:
    ts = _utcnow()
    turns = tuple(
        TurnSnapshot(iteration=i, turn_type="user_prompt", input_prompt=f"p{i}")
        for i in range(n_turns)
    )
    tools = tuple(
        ToolCallRecord(iteration=i, tool_name=f"tool_{i}")
        for i in range(n_tools)
    )
    metrics = (
        Metric(name="turns_total", value=float(n_turns), unit="count"),
        Metric(name="cost_premium_requests", value=1.5, unit="requests"),
    )
    return RunRecord(
        run_id=run_id,
        config=RunConfig(model=model),
        outcome=outcome,
        started_at=ts,
        turns=turns,
        tool_calls=tools,
        metrics=metrics,
    )


# ── CSV Export ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRunsToCsv:
    def test_basic(self):
        runs = [_make_run("r1"), _make_run("r2")]
        result = runs_to_csv(runs)
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 3  # header + 2 data rows
        header = rows[0]
        assert "run_id" in header
        assert "turns_total" in header
        assert "cost_premium_requests" in header

    def test_specific_metrics(self):
        runs = [_make_run()]
        result = runs_to_csv(runs, metric_names=["turns_total"])
        reader = csv.reader(io.StringIO(result))
        header = list(reader)[0]
        assert "turns_total" in header
        assert "cost_premium_requests" not in header

    def test_empty(self):
        assert runs_to_csv([]) == ""

    def test_run_id_in_rows(self):
        runs = [_make_run("test_123")]
        result = runs_to_csv(runs)
        assert "test_123" in result


# ── JSONL Export ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestRunsToJsonl:
    def test_basic(self):
        runs = [_make_run("r1"), _make_run("r2")]
        result = runs_to_jsonl(runs)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        parsed = json.loads(lines[0])
        assert parsed["run_id"] == "r1"

    def test_empty(self):
        assert runs_to_jsonl([]) == ""

    def test_valid_json_per_line(self):
        runs = [_make_run("r1")]
        result = runs_to_jsonl(runs)
        for line in result.strip().split("\n"):
            json.loads(line)  # should not raise


# ── Summary Export ────────────────────────────────────────────────────


@pytest.mark.unit
class TestRunToSummary:
    def test_basic(self):
        run = _make_run("r1", model="gpt-4.1")
        summary = run_to_summary(run)
        assert summary["run_id"] == "r1"
        assert summary["c_model"] == "gpt-4.1"
        assert summary["m_turns_total"] == 2.0
        assert summary["m_cost_premium_requests"] == 1.5
        assert summary["turns_count"] == 2
        assert summary["tool_calls_count"] == 1

    def test_config_fields(self):
        run = _make_run()
        summary = run_to_summary(run)
        assert "c_max_iterations" in summary
        assert "c_context_budget" in summary
        assert "c_discovery_top_k" in summary

    def test_outcome(self):
        run = _make_run(outcome=RunOutcome.FAILURE)
        summary = run_to_summary(run)
        assert summary["outcome"] == "failure"


@pytest.mark.unit
class TestRunsToSummaryDicts:
    def test_multiple(self):
        runs = [_make_run("r1"), _make_run("r2")]
        dicts = runs_to_summary_dicts(runs)
        assert len(dicts) == 2
        assert dicts[0]["run_id"] == "r1"
        assert dicts[1]["run_id"] == "r2"


# ── File Export ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestSaveCsv:
    def test_creates_file(self, tmp_path):
        path = tmp_path / "out.csv"
        save_csv([_make_run()], path)
        assert path.exists()
        content = path.read_text()
        assert "run_id" in content

    def test_creates_directories(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "out.csv"
        save_csv([_make_run()], path)
        assert path.exists()


@pytest.mark.unit
class TestSaveJsonl:
    def test_creates_file(self, tmp_path):
        path = tmp_path / "out.jsonl"
        save_jsonl([_make_run()], path)
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert "run_id" in parsed


# ── Raw Event Export ──────────────────────────────────────────────────


@pytest.mark.unit
class TestRawEventsToJsonl:
    def test_basic(self, tmp_path):
        store = EvalStore(tmp_path / "test.db")
        try:
            # Insert a run first (FK constraint)
            run = _make_run("r1")
            store.save_run(run)
            store.save_raw_event(RawEvent(
                run_id="r1", event_type="test", payload={"key": "value"},
            ))
            path = tmp_path / "events.jsonl"
            count = raw_events_to_jsonl(store, path, run_id="r1")
            assert count >= 1
            assert path.exists()
        finally:
            store.close()


# ── Metrics Long-Format CSV ──────────────────────────────────────────


@pytest.mark.unit
class TestMetricsToCsv:
    def test_basic(self, tmp_path):
        path = tmp_path / "metrics.csv"
        runs = [_make_run("r1"), _make_run("r2")]
        metrics_to_csv(runs, path)
        assert path.exists()
        content = path.read_text()
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        header = rows[0]
        assert "metric_name" in header
        assert "value" in header
        # 2 runs × 2 metrics each = 4 data rows + 1 header
        assert len(rows) == 5
