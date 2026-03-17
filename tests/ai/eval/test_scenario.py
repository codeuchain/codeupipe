"""Unit tests for codeupipe.ai.eval.scenario — scenario management."""

import json
import pytest

from codeupipe.ai.eval.scenario import (
    ScenarioVerdict,
    build_scenario,
    check_expectations,
    load_scenarios_from_json,
    save_scenarios_to_json,
)
from codeupipe.ai.eval.types import (
    Metric,
    RunConfig,
    RunOutcome,
    RunRecord,
    ScenarioCategory,
    ScenarioExpectations,
    ToolCallRecord,
    TurnSnapshot,
    _utcnow,
)


def _make_run(
    *,
    turns: int = 3,
    outcome: RunOutcome = RunOutcome.SUCCESS,
    tool_names: tuple[str, ...] = ("echo", "file_read"),
    response: str = "The answer is 42",
) -> RunRecord:
    """Build a minimal RunRecord for scenario testing."""
    now = _utcnow()
    turn_list = tuple(
        TurnSnapshot(
            iteration=i,
            turn_type="user_prompt" if i == 0 else "follow_up",
            input_prompt="test prompt",
            response_content=response,
        )
        for i in range(turns)
    )
    tc_list = tuple(
        ToolCallRecord(iteration=i + 1, tool_name=name)
        for i, name in enumerate(tool_names)
    )

    return RunRecord(
        run_id="test_run",
        config=RunConfig(),
        started_at=now,
        ended_at=now,
        outcome=outcome,
        turns=turn_list,
        tool_calls=tc_list,
        metrics=(
            Metric(name="cost_premium_requests", value=3.0),
        ),
    )


@pytest.mark.unit
class TestBuildScenario:
    def test_minimal(self):
        s = build_scenario("test", "do something")
        assert s.name == "test"
        assert s.input_prompt == "do something"
        assert s.category == ScenarioCategory.STANDARD

    def test_all_options(self):
        s = build_scenario(
            "full test",
            "complex prompt",
            category=ScenarioCategory.ADVERSARIAL,
            max_turns=5,
            max_cost=10.0,
            required_tools=["echo"],
            forbidden_tools=["rm"],
            output_contains=["success"],
            output_not_contains=["error"],
            must_complete=True,
            tags=["perf"],
            description="full scenario",
            metadata={"author": "test"},
        )
        assert s.category == ScenarioCategory.ADVERSARIAL
        assert s.expectations.max_turns == 5
        assert s.expectations.max_cost == 10.0
        assert s.expectations.required_tool_calls == ("echo",)
        assert s.expectations.forbidden_tool_calls == ("rm",)
        assert s.expectations.output_contains == ("success",)
        assert s.expectations.output_not_contains == ("error",)
        assert s.tags == ("perf",)


@pytest.mark.unit
class TestCheckExpectations:
    """Tests for scenario expectation checking."""

    def test_max_turns_pass(self):
        scenario = build_scenario("t", "p", max_turns=5)
        run = _make_run(turns=3)
        verdicts = check_expectations(scenario, run)

        turns_verdict = [v for v in verdicts if v.check == "max_turns"]
        assert len(turns_verdict) == 1
        assert turns_verdict[0].passed is True

    def test_max_turns_fail(self):
        scenario = build_scenario("t", "p", max_turns=2)
        run = _make_run(turns=5)
        verdicts = check_expectations(scenario, run)

        turns_verdict = [v for v in verdicts if v.check == "max_turns"]
        assert turns_verdict[0].passed is False

    def test_max_cost_pass(self):
        scenario = build_scenario("t", "p", max_cost=5.0)
        run = _make_run()
        verdicts = check_expectations(scenario, run)

        cost_verdict = [v for v in verdicts if v.check == "max_cost"]
        assert len(cost_verdict) == 1
        assert cost_verdict[0].passed is True  # 3.0 <= 5.0

    def test_max_cost_fail(self):
        scenario = build_scenario("t", "p", max_cost=1.0)
        run = _make_run()
        verdicts = check_expectations(scenario, run)

        cost_verdict = [v for v in verdicts if v.check == "max_cost"]
        assert cost_verdict[0].passed is False  # 3.0 > 1.0

    def test_required_tool_pass(self):
        scenario = build_scenario("t", "p", required_tools=["echo"])
        run = _make_run(tool_names=("echo", "file_read"))
        verdicts = check_expectations(scenario, run)

        tool_verdict = [v for v in verdicts if v.check == "required_tool"]
        assert tool_verdict[0].passed is True

    def test_required_tool_fail(self):
        scenario = build_scenario("t", "p", required_tools=["deploy"])
        run = _make_run(tool_names=("echo",))
        verdicts = check_expectations(scenario, run)

        tool_verdict = [v for v in verdicts if v.check == "required_tool"]
        assert tool_verdict[0].passed is False

    def test_forbidden_tool_pass(self):
        scenario = build_scenario("t", "p", forbidden_tools=["rm"])
        run = _make_run(tool_names=("echo",))
        verdicts = check_expectations(scenario, run)

        verdict = [v for v in verdicts if v.check == "forbidden_tool"]
        assert verdict[0].passed is True

    def test_forbidden_tool_fail(self):
        scenario = build_scenario("t", "p", forbidden_tools=["echo"])
        run = _make_run(tool_names=("echo",))
        verdicts = check_expectations(scenario, run)

        verdict = [v for v in verdicts if v.check == "forbidden_tool"]
        assert verdict[0].passed is False

    def test_output_contains_pass(self):
        scenario = build_scenario("t", "p", output_contains=["42"])
        run = _make_run(response="The answer is 42")
        verdicts = check_expectations(scenario, run)

        verdict = [v for v in verdicts if v.check == "output_contains"]
        assert verdict[0].passed is True

    def test_output_contains_fail(self):
        scenario = build_scenario("t", "p", output_contains=["99"])
        run = _make_run(response="The answer is 42")
        verdicts = check_expectations(scenario, run)

        verdict = [v for v in verdicts if v.check == "output_contains"]
        assert verdict[0].passed is False

    def test_output_not_contains_pass(self):
        scenario = build_scenario("t", "p", output_not_contains=["error"])
        run = _make_run(response="All good")
        verdicts = check_expectations(scenario, run)

        verdict = [v for v in verdicts if v.check == "output_not_contains"]
        assert verdict[0].passed is True

    def test_output_not_contains_fail(self):
        scenario = build_scenario("t", "p", output_not_contains=["error"])
        run = _make_run(response="Something went error")
        verdicts = check_expectations(scenario, run)

        verdict = [v for v in verdicts if v.check == "output_not_contains"]
        assert verdict[0].passed is False

    def test_must_complete_pass(self):
        scenario = build_scenario("t", "p", must_complete=True)
        run = _make_run(outcome=RunOutcome.SUCCESS)
        verdicts = check_expectations(scenario, run)

        verdict = [v for v in verdicts if v.check == "must_complete"]
        assert verdict[0].passed is True

    def test_must_complete_fail(self):
        scenario = build_scenario("t", "p", must_complete=True)
        run = _make_run(outcome=RunOutcome.TIMEOUT)
        verdicts = check_expectations(scenario, run)

        verdict = [v for v in verdicts if v.check == "must_complete"]
        assert verdict[0].passed is False

    def test_no_expectations(self):
        scenario = build_scenario("t", "p", must_complete=False)
        run = _make_run()
        verdicts = check_expectations(scenario, run)
        assert verdicts == []  # nothing to check

    def test_case_insensitive_output(self):
        scenario = build_scenario("t", "p", output_contains=["ANSWER"])
        run = _make_run(response="the answer is here")
        verdicts = check_expectations(scenario, run)

        verdict = [v for v in verdicts if v.check == "output_contains"]
        assert verdict[0].passed is True


@pytest.mark.unit
class TestScenarioVerdict:
    def test_repr_pass(self):
        v = ScenarioVerdict("test", True, detail="passed")
        assert "PASS" in repr(v)

    def test_repr_fail(self):
        v = ScenarioVerdict("test", False, detail="failed")
        assert "FAIL" in repr(v)

    def test_to_dict(self):
        v = ScenarioVerdict("max_turns", True, expected="5", actual="3")
        d = v.to_dict()
        assert d["check"] == "max_turns"
        assert d["passed"] is True


@pytest.mark.unit
class TestScenarioIO:
    """Tests for JSON load/save."""

    def test_save_and_load(self, tmp_path):
        scenarios = [
            build_scenario("test1", "prompt1", max_turns=5, tags=["a"]),
            build_scenario("test2", "prompt2", category=ScenarioCategory.EDGE_CASE),
        ]

        path = tmp_path / "scenarios.json"
        save_scenarios_to_json(scenarios, path)

        # Verify the file is valid JSON
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 2

        # Load back
        loaded = load_scenarios_from_json(path)
        assert len(loaded) == 2
        assert loaded[0].name == "test1"
        assert loaded[0].expectations.max_turns == 5
        assert loaded[1].category == ScenarioCategory.EDGE_CASE

    def test_load_missing_file(self, tmp_path):
        loaded = load_scenarios_from_json(tmp_path / "nonexistent.json")
        assert loaded == []
