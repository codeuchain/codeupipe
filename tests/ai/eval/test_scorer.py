"""Unit tests for codeupipe.ai.eval.scorer — deterministic + LLM scoring."""

import json

import pytest

from codeupipe.ai.eval.scenario import build_scenario
from codeupipe.ai.eval.scorer import (
    DEFAULT_DIMENSIONS,
    ScoreDimension,
    ScoreResult,
    build_judge_prompt,
    compute_weighted_average,
    parse_judge_response,
    score_deterministic,
    score_with_judge_response,
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
    turns: int = 2,
    outcome: RunOutcome = RunOutcome.SUCCESS,
    tool_names: tuple[str, ...] = ("echo",),
    response: str = "Done successfully",
) -> RunRecord:
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
        metrics=(Metric(name="cost_premium_requests", value=2.0),),
    )


@pytest.mark.unit
class TestScoreDeterministic:
    """Tests for deterministic scoring."""

    def test_all_pass(self):
        scenario = build_scenario(
            "test", "p",
            max_turns=5,
            required_tools=["echo"],
            output_contains=["success"],
        )
        run = _make_run(turns=2, tool_names=("echo",), response="Done successfully")
        result = score_deterministic(run, scenario)

        assert result.pass_rate == 100.0
        assert result.verdicts_passed == result.verdicts_total

    def test_partial_pass(self):
        scenario = build_scenario(
            "test", "p",
            max_turns=1,  # will fail: run has 2 turns
            required_tools=["echo"],  # will pass
        )
        run = _make_run(turns=2, tool_names=("echo",))
        result = score_deterministic(run, scenario)

        assert result.verdicts_passed < result.verdicts_total
        assert 0 < result.pass_rate < 100.0

    def test_no_scenario(self):
        run = _make_run()
        result = score_deterministic(run)

        assert result.pass_rate == 100.0  # no expectations = 100%
        assert result.verdicts_total == 0

    def test_score_result_to_dict(self):
        run = _make_run()
        result = score_deterministic(run)
        d = result.to_dict()
        assert "run_id" in d
        assert "pass_rate" in d

    def test_score_result_to_metrics(self):
        scenario = build_scenario("t", "p", max_turns=5)
        run = _make_run()
        result = score_deterministic(run, scenario)

        metrics = result.to_metrics()
        names = {m.name for m in metrics}
        assert "score_weighted_avg" in names
        assert "score_pass_rate" in names


@pytest.mark.unit
class TestBuildJudgePrompt:
    """Tests for LLM judge prompt generation."""

    def test_basic_prompt(self):
        run = _make_run(response="Hello world")
        prompt = build_judge_prompt(run)

        assert "Hello world" in prompt
        assert "correctness" in prompt
        assert "helpfulness" in prompt
        assert "JSON" in prompt

    def test_with_scenario(self):
        scenario = build_scenario("math test", "Calculate 2+2")
        run = _make_run()
        prompt = build_judge_prompt(run, scenario)

        assert "math test" in prompt
        assert "Calculate 2+2" in prompt

    def test_custom_dimensions(self):
        dims = (
            ScoreDimension(name="accuracy", description="Is it accurate?", weight=0.5),
            ScoreDimension(name="speed", description="Is it fast?", weight=0.5),
        )
        run = _make_run()
        prompt = build_judge_prompt(run, dimensions=dims)

        assert "accuracy" in prompt
        assert "speed" in prompt
        assert "correctness" not in prompt

    def test_includes_context(self):
        run = _make_run(turns=3, tool_names=("echo", "file_read"))
        prompt = build_judge_prompt(run)

        assert "Turns taken: 3" in prompt
        assert "echo" in prompt
        assert "file_read" in prompt


@pytest.mark.unit
class TestParseJudgeResponse:
    """Tests for parsing judge model JSON responses."""

    def test_valid_json(self):
        response = json.dumps({
            "reasoning": "Good output",
            "scores": {
                "correctness": 4.5,
                "helpfulness": 4.0,
                "completeness": 3.5,
                "conciseness": 4.0,
                "safety": 5.0,
            }
        })
        scores, reasoning = parse_judge_response(response)

        assert scores["correctness"] == 4.5
        assert scores["safety"] == 5.0
        assert reasoning == "Good output"

    def test_markdown_wrapped(self):
        response = """```json
{
    "reasoning": "OK",
    "scores": {
        "correctness": 3.0,
        "helpfulness": 3.0,
        "completeness": 3.0,
        "conciseness": 3.0,
        "safety": 5.0
    }
}
```"""
        scores, reasoning = parse_judge_response(response)
        assert scores["correctness"] == 3.0
        assert reasoning == "OK"

    def test_clamped_scores(self):
        response = json.dumps({
            "reasoning": "extreme",
            "scores": {
                "correctness": 99.0,  # above max
                "helpfulness": 0.0,    # below min
            }
        })
        scores, _ = parse_judge_response(response)
        assert scores["correctness"] == 5.0
        assert scores["helpfulness"] == 1.0

    def test_invalid_json(self):
        scores, reasoning = parse_judge_response("not json at all")
        assert scores == {}
        assert reasoning == ""

    def test_custom_dimensions(self):
        dims = (
            ScoreDimension(name="custom_dim", description="test", weight=1.0, min_score=0, max_score=10),
        )
        response = json.dumps({
            "reasoning": "ok",
            "scores": {"custom_dim": 7.5},
        })
        scores, _ = parse_judge_response(response, dims)
        assert scores["custom_dim"] == 7.5


@pytest.mark.unit
class TestComputeWeightedAverage:
    def test_equal_weights(self):
        dims = (
            ScoreDimension(name="a", description="", weight=1.0),
            ScoreDimension(name="b", description="", weight=1.0),
        )
        avg = compute_weighted_average({"a": 4.0, "b": 2.0}, dims)
        assert avg == 3.0

    def test_unequal_weights(self):
        dims = (
            ScoreDimension(name="a", description="", weight=3.0),
            ScoreDimension(name="b", description="", weight=1.0),
        )
        avg = compute_weighted_average({"a": 4.0, "b": 2.0}, dims)
        # (4*3 + 2*1) / (3+1) = 14/4 = 3.5
        assert avg == 3.5

    def test_empty(self):
        assert compute_weighted_average({}) == 0.0


@pytest.mark.unit
class TestScoreWithJudgeResponse:
    def test_combined_scoring(self):
        scenario = build_scenario(
            "test", "p",
            max_turns=5,
            required_tools=["echo"],
        )
        run = _make_run(tool_names=("echo",))

        judge_response = json.dumps({
            "reasoning": "Good quality",
            "scores": {
                "correctness": 4.0,
                "helpfulness": 3.5,
                "completeness": 4.0,
                "conciseness": 3.0,
                "safety": 5.0,
            }
        })

        result = score_with_judge_response(
            run,
            judge_response,
            judge_model="gpt-4.1",
            scenario=scenario,
        )

        assert result.dimension_scores["correctness"] == 4.0
        assert result.weighted_average > 0
        assert result.judge_model == "gpt-4.1"
        assert result.judge_reasoning == "Good quality"
        # Deterministic verdicts should also be present
        assert result.verdicts_total >= 2  # max_turns + required_tool + must_complete
        assert result.pass_rate == 100.0
