"""Unit tests for codeupipe.ai.eval.types — frozen dataclasses."""

import pytest
from datetime import datetime, timezone

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
    _new_id,
    _utcnow,
)


class TestRunConfig:
    def test_defaults(self):
        cfg = RunConfig()
        assert cfg.model == "gpt-4.1"
        assert cfg.max_iterations == 10
        assert cfg.context_budget == 128_000
        assert cfg.directives == ()
        assert cfg.extra == {}

    def test_custom_values(self):
        cfg = RunConfig(
            model="claude-sonnet-4",
            max_iterations=5,
            context_budget=64_000,
            directives=("focus on tests",),
            extra={"temperature": 0.7},
        )
        assert cfg.model == "claude-sonnet-4"
        assert cfg.max_iterations == 5
        assert cfg.directives == ("focus on tests",)
        assert cfg.extra["temperature"] == 0.7

    def test_frozen(self):
        cfg = RunConfig()
        with pytest.raises(AttributeError):
            cfg.model = "changed"

    def test_to_dict(self):
        cfg = RunConfig(model="gpt-5")
        d = cfg.to_dict()
        assert d["model"] == "gpt-5"
        assert isinstance(d["directives"], list)


class TestTurnSnapshot:
    def test_defaults(self):
        turn = TurnSnapshot(iteration=0, turn_type="user_prompt", input_prompt="hello")
        assert turn.iteration == 0
        assert turn.turn_type == "user_prompt"
        assert turn.tokens_estimated == 0
        assert turn.raw_data == {}

    def test_to_dict(self):
        turn = TurnSnapshot(
            iteration=1,
            turn_type="follow_up",
            input_prompt="continue",
            response_content="done",
            tool_calls_count=2,
            tokens_estimated=100,
            duration_ms=500.0,
            model_used="gpt-4.1",
        )
        d = turn.to_dict()
        assert d["iteration"] == 1
        assert d["response_content"] == "done"
        assert d["tool_calls_count"] == 2

    def test_frozen(self):
        turn = TurnSnapshot(iteration=0, turn_type="user_prompt", input_prompt="test")
        with pytest.raises(AttributeError):
            turn.iteration = 5


class TestToolCallRecord:
    def test_defaults(self):
        tc = ToolCallRecord(iteration=0, tool_name="echo")
        assert tc.tool_name == "echo"
        assert tc.success is True
        assert tc.server_name == ""

    def test_to_dict(self):
        tc = ToolCallRecord(
            iteration=1,
            tool_name="file_write",
            server_name="fs-server",
            arguments={"path": "/tmp/test"},
            result_summary="written",
            duration_ms=120.0,
            success=True,
        )
        d = tc.to_dict()
        assert d["tool_name"] == "file_write"
        assert d["success"] is True


class TestMetric:
    def test_basic(self):
        m = Metric(name="turns_total", value=5.0, unit="count")
        assert m.name == "turns_total"
        assert m.value == 5.0
        assert m.tags == ()

    def test_with_tags(self):
        m = Metric(name="model_turns_gpt-4.1", value=3.0, tags=("gpt-4.1",))
        assert m.tags == ("gpt-4.1",)

    def test_to_dict(self):
        m = Metric(name="cost", value=1.5, unit="premium_requests")
        d = m.to_dict()
        assert d["name"] == "cost"
        assert d["value"] == 1.5


class TestRunRecord:
    def test_defaults(self):
        run = RunRecord()
        assert run.run_id  # auto-generated
        assert run.outcome == RunOutcome.UNKNOWN
        assert run.turns == ()
        assert run.tool_calls == ()
        assert run.metrics == ()

    def test_with_data(self):
        turn = TurnSnapshot(iteration=0, turn_type="user_prompt", input_prompt="test")
        tc = ToolCallRecord(iteration=0, tool_name="echo")
        m = Metric(name="turns_total", value=1.0)

        run = RunRecord(
            run_id="test_run_1",
            session_id="sess_1",
            scenario_id="sc_1",
            config=RunConfig(model="claude-sonnet-4"),
            outcome=RunOutcome.SUCCESS,
            turns=(turn,),
            tool_calls=(tc,),
            metrics=(m,),
        )
        assert run.run_id == "test_run_1"
        assert len(run.turns) == 1
        assert run.outcome == RunOutcome.SUCCESS

    def test_to_dict(self):
        run = RunRecord(run_id="test_run_2")
        d = run.to_dict()
        assert d["run_id"] == "test_run_2"
        assert d["outcome"] == "unknown"
        assert isinstance(d["turns"], list)


class TestScenario:
    def test_build(self):
        s = Scenario(
            name="basic test",
            input_prompt="hello",
            category=ScenarioCategory.STANDARD,
        )
        assert s.name == "basic test"
        assert s.category == ScenarioCategory.STANDARD

    def test_expectations(self):
        exp = ScenarioExpectations(
            max_turns=5,
            required_tool_calls=("echo",),
            output_contains=("success",),
        )
        assert exp.max_turns == 5
        assert exp.required_tool_calls == ("echo",)


class TestBaseline:
    def test_basic(self):
        b = Baseline(
            name="default",
            metrics={"turns_total": 3.5},
            run_count=10,
        )
        assert b.name == "default"
        assert b.metrics["turns_total"] == 3.5
        assert b.run_count == 10


class TestExperiment:
    def test_basic(self):
        e = Experiment(
            name="model-compare",
            configs=(RunConfig(model="gpt-4.1"), RunConfig(model="claude-sonnet-4")),
            status=ExperimentStatus.PENDING,
        )
        assert e.name == "model-compare"
        assert len(e.configs) == 2


class TestRawEvent:
    def test_basic(self):
        ev = RawEvent(
            run_id="r1",
            event_type="audit",
            payload={"link_name": "SendTurnLink", "duration_ms": 1200},
        )
        assert ev.event_type == "audit"
        assert ev.payload["link_name"] == "SendTurnLink"


class TestHelpers:
    def test_new_id_uniqueness(self):
        ids = {_new_id() for _ in range(100)}
        assert len(ids) == 100

    def test_utcnow(self):
        now = _utcnow()
        assert now.tzinfo == timezone.utc
