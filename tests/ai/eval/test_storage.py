"""Unit tests for codeupipe.ai.eval.storage — SQLite persistence."""

import json

import pytest

from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    Baseline,
    Experiment,
    ExperimentStatus,
    Metric,
    RawEvent,
    RunConfig,
    RunOutcome,
    RunRecord,
    Scenario,
    ScenarioCategory,
    ScenarioExpectations,
    ToolCallRecord,
    TurnSnapshot,
    _utcnow,
)


@pytest.fixture
def store(tmp_path):
    """Fresh EvalStore backed by a temp file."""
    s = EvalStore(tmp_path / "test_eval.db")
    yield s
    s.close()


def _make_run(
    run_id: str = "run_1",
    *,
    outcome: RunOutcome = RunOutcome.SUCCESS,
    turns: int = 2,
    tools: int = 1,
    extra_metrics: list[Metric] | None = None,
) -> RunRecord:
    """Build a minimal RunRecord for testing."""
    now = _utcnow()
    turn_list = tuple(
        TurnSnapshot(
            iteration=i,
            turn_type="user_prompt" if i == 0 else "follow_up",
            input_prompt=f"prompt_{i}",
            response_content=f"response_{i}",
            tool_calls_count=1 if i > 0 else 0,
            tokens_estimated=100,
            duration_ms=500.0,
            model_used="gpt-4.1",
        )
        for i in range(turns)
    )
    tc_list = tuple(
        ToolCallRecord(
            iteration=i + 1,
            tool_name=f"tool_{i}",
            server_name="test_server",
            arguments={"arg": i},
            result_summary="ok",
            duration_ms=100.0,
            success=True,
        )
        for i in range(tools)
    )
    metrics = list(extra_metrics or [])
    metrics.append(Metric(name="turns_total", value=float(turns), unit="count"))
    metrics.append(Metric(name="tool_calls_total", value=float(tools), unit="count"))

    return RunRecord(
        run_id=run_id,
        session_id="sess_1",
        scenario_id="sc_1",
        config=RunConfig(model="gpt-4.1"),
        started_at=now,
        ended_at=now,
        outcome=outcome,
        turns=turn_list,
        tool_calls=tc_list,
        metrics=tuple(metrics),
        audit_events=({"link": "TestLink", "duration_ms": 50},),
        raw_data={"test_key": "test_value"},
    )


@pytest.mark.unit
class TestEvalStoreRuns:
    """Tests for run CRUD operations."""

    def test_save_and_get(self, store):
        run = _make_run("r1")
        store.save_run(run)

        loaded = store.get_run("r1")
        assert loaded is not None
        assert loaded.run_id == "r1"
        assert loaded.session_id == "sess_1"
        assert loaded.outcome == RunOutcome.SUCCESS
        assert loaded.config.model == "gpt-4.1"

    def test_turns_persist(self, store):
        run = _make_run("r2", turns=3)
        store.save_run(run)

        loaded = store.get_run("r2")
        assert len(loaded.turns) == 3
        assert loaded.turns[0].turn_type == "user_prompt"
        assert loaded.turns[1].turn_type == "follow_up"
        assert loaded.turns[2].input_prompt == "prompt_2"

    def test_tool_calls_persist(self, store):
        run = _make_run("r3", tools=2)
        store.save_run(run)

        loaded = store.get_run("r3")
        assert len(loaded.tool_calls) == 2
        assert loaded.tool_calls[0].tool_name == "tool_0"
        assert loaded.tool_calls[1].server_name == "test_server"
        assert loaded.tool_calls[0].success is True

    def test_metrics_persist(self, store):
        run = _make_run("r4")
        store.save_run(run)

        loaded = store.get_run("r4")
        names = {m.name for m in loaded.metrics}
        assert "turns_total" in names
        assert "tool_calls_total" in names

    def test_raw_data_persists(self, store):
        run = _make_run("r5")
        store.save_run(run)

        loaded = store.get_run("r5")
        assert loaded.raw_data["test_key"] == "test_value"

    def test_audit_events_persist(self, store):
        run = _make_run("r6")
        store.save_run(run)

        loaded = store.get_run("r6")
        assert len(loaded.audit_events) == 1
        assert loaded.audit_events[0]["link"] == "TestLink"

    def test_get_nonexistent(self, store):
        assert store.get_run("nope") is None

    def test_list_runs(self, store):
        store.save_run(_make_run("r1"))
        store.save_run(_make_run("r2"))
        store.save_run(_make_run("r3"))

        runs = store.list_runs()
        assert len(runs) == 3

    def test_list_runs_filter_scenario(self, store):
        store.save_run(_make_run("r1"))
        runs = store.list_runs(scenario_id="sc_1")
        assert len(runs) == 1
        assert runs[0].run_id == "r1"

    def test_list_runs_filter_outcome(self, store):
        store.save_run(_make_run("r1", outcome=RunOutcome.SUCCESS))
        store.save_run(_make_run("r2", outcome=RunOutcome.FAILURE))

        success_runs = store.list_runs(outcome=RunOutcome.SUCCESS)
        assert len(success_runs) == 1
        assert success_runs[0].outcome == RunOutcome.SUCCESS

    def test_upsert_on_save(self, store):
        """save_run with same ID replaces existing."""
        store.save_run(_make_run("r1", outcome=RunOutcome.UNKNOWN))
        store.save_run(_make_run("r1", outcome=RunOutcome.SUCCESS))
        loaded = store.get_run("r1")
        assert loaded.outcome == RunOutcome.SUCCESS


@pytest.mark.unit
class TestEvalStoreRawEvents:
    """Tests for raw event storage."""

    def test_save_and_count(self, store):
        # Insert a run first so FK is satisfied
        store.save_run(_make_run("r1"))
        ev = RawEvent(run_id="r1", event_type="test", payload={"key": "val"})
        store.save_raw_event(ev)

        assert store.count_raw_events(run_id="r1") >= 1
        assert store.count_raw_events(event_type="test") == 1
        assert store.count_raw_events(event_type="other") == 0

    def test_get_raw_events(self, store):
        store.save_run(_make_run("r1"))
        for i in range(5):
            store.save_raw_event(RawEvent(
                run_id="r1",
                event_type="loop" if i % 2 == 0 else "tool",
                payload={"i": i},
            ))

        loop_events = store.get_raw_events(run_id="r1", event_type="loop")
        assert len(loop_events) == 3

        tool_events = store.get_raw_events(run_id="r1", event_type="tool")
        assert len(tool_events) == 2

    def test_limit(self, store):
        store.save_run(_make_run("r1"))
        for i in range(10):
            store.save_raw_event(RawEvent(
                run_id="r1", event_type="data", payload={"i": i},
            ))

        limited = store.get_raw_events(run_id="r1", event_type="data", limit=3)
        assert len(limited) == 3


@pytest.mark.unit
class TestEvalStoreMetricValues:
    """Tests for cross-run metric queries."""

    def test_get_metric_values(self, store):
        store.save_run(_make_run("r1", turns=2))
        store.save_run(_make_run("r2", turns=5))

        values = store.get_metric_values("turns_total")
        assert len(values) == 2
        assert 2.0 in values
        assert 5.0 in values

    def test_filter_by_scenario(self, store):
        store.save_run(_make_run("r1"))
        values = store.get_metric_values("turns_total", scenario_id="sc_1")
        assert len(values) == 1

        values = store.get_metric_values("turns_total", scenario_id="other")
        assert len(values) == 0


@pytest.mark.unit
class TestEvalStoreScenarios:
    """Tests for scenario persistence."""

    def test_save_and_get(self, store):
        s = Scenario(
            scenario_id="sc_1",
            name="test scenario",
            description="a test",
            input_prompt="do something",
            category=ScenarioCategory.STANDARD,
            expectations=ScenarioExpectations(
                max_turns=5,
                required_tool_calls=("echo",),
            ),
            tags=("basic",),
            metadata={"author": "test"},
        )
        store.save_scenario(s)

        loaded = store.get_scenario("sc_1")
        assert loaded is not None
        assert loaded.name == "test scenario"
        assert loaded.category == ScenarioCategory.STANDARD
        assert loaded.expectations.max_turns == 5
        assert loaded.expectations.required_tool_calls == ("echo",)
        assert loaded.tags == ("basic",)

    def test_get_nonexistent(self, store):
        assert store.get_scenario("nope") is None

    def test_list_scenarios(self, store):
        store.save_scenario(Scenario(
            scenario_id="sc_1", name="a",
            category=ScenarioCategory.STANDARD,
        ))
        store.save_scenario(Scenario(
            scenario_id="sc_2", name="b",
            category=ScenarioCategory.EDGE_CASE,
        ))
        store.save_scenario(Scenario(
            scenario_id="sc_3", name="c",
            category=ScenarioCategory.STANDARD,
        ))

        all_s = store.list_scenarios()
        assert len(all_s) == 3

        standard = store.list_scenarios(category="standard")
        assert len(standard) == 2


@pytest.mark.unit
class TestEvalStoreBaselines:
    """Tests for baseline persistence."""

    def test_save_and_get(self, store):
        b = Baseline(
            baseline_id="bl_1",
            name="default",
            config=RunConfig(model="gpt-4.1"),
            metrics={"turns_total": 3.5, "cost_premium_requests": 2.0},
            run_count=10,
            run_ids=("r1", "r2"),
        )
        store.save_baseline(b)

        loaded = store.get_baseline("bl_1")
        assert loaded is not None
        assert loaded.name == "default"
        assert loaded.metrics["turns_total"] == 3.5
        assert loaded.run_count == 10
        assert loaded.run_ids == ("r1", "r2")

    def test_latest_baseline(self, store):
        store.save_baseline(Baseline(
            baseline_id="bl_1", name="default",
            metrics={"turns_total": 3.0}, run_count=5,
        ))
        store.save_baseline(Baseline(
            baseline_id="bl_2", name="default",
            metrics={"turns_total": 4.0}, run_count=8,
        ))

        latest = store.get_latest_baseline("default")
        assert latest is not None
        assert latest.baseline_id == "bl_2"

    def test_latest_baseline_not_found(self, store):
        assert store.get_latest_baseline("nope") is None


@pytest.mark.unit
class TestEvalStoreExperiments:
    """Tests for experiment persistence."""

    def test_save_and_get(self, store):
        e = Experiment(
            experiment_id="exp_1",
            name="model-compare",
            description="comparing models",
            configs=(RunConfig(model="gpt-4.1"), RunConfig(model="claude-sonnet-4")),
            scenario_ids=("sc_1",),
            status=ExperimentStatus.PENDING,
            run_ids=("r1", "r2"),
        )
        store.save_experiment(e)

        loaded = store.get_experiment("exp_1")
        assert loaded is not None
        assert loaded.name == "model-compare"
        assert len(loaded.configs) == 2
        assert loaded.configs[0].model == "gpt-4.1"
        assert loaded.configs[1].model == "claude-sonnet-4"
        assert loaded.scenario_ids == ("sc_1",)
        assert loaded.status == "pending"

    def test_get_nonexistent(self, store):
        assert store.get_experiment("nope") is None
