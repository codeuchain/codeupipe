"""Unit tests for codeupipe.ai.eval.validation — data integrity checks."""

from datetime import timedelta

import pytest

from codeupipe.ai.eval.types import (
    Metric,
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
from codeupipe.ai.eval.validation import (
    ValidationError,
    is_valid_run,
    is_valid_scenario,
    validate_metric,
    validate_run,
    validate_scenario,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _valid_run(**overrides) -> RunRecord:
    now = _utcnow()
    defaults = dict(
        run_id="r1",
        config=RunConfig(model="gpt-4.1"),
        outcome=RunOutcome.SUCCESS,
        started_at=now,
        ended_at=now + timedelta(seconds=5),
        turns=(
            TurnSnapshot(
                iteration=0,
                turn_type="user_prompt",
                input_prompt="hello",
                tokens_estimated=100,
                duration_ms=50.0,
            ),
            TurnSnapshot(
                iteration=1,
                turn_type="follow_up",
                input_prompt="world",
                tokens_estimated=200,
                duration_ms=30.0,
            ),
        ),
        metrics=(
            Metric(name="turns_total", value=2.0),
            Metric(name="tokens_total", value=300.0),
        ),
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


def _valid_scenario(**overrides) -> Scenario:
    defaults = dict(
        scenario_id="sc_1",
        name="Test Scenario",
        description="A test",
        input_prompt="Do the thing",
        category=ScenarioCategory.STANDARD,
        expectations=ScenarioExpectations(),
    )
    defaults.update(overrides)
    return Scenario(**defaults)


# ── validate_run ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestValidateRun:
    def test_valid_run_no_errors(self):
        errors = validate_run(_valid_run())
        error_only = [e for e in errors if e.severity == "error"]
        assert error_only == []

    def test_empty_run_id(self):
        errors = validate_run(_valid_run(run_id=""))
        assert any(e.field == "run_id" for e in errors)

    def test_missing_config_model(self):
        errors = validate_run(_valid_run(config=RunConfig(model="")))
        assert any("model" in e.field for e in errors)

    def test_ended_before_started(self):
        now = _utcnow()
        errors = validate_run(_valid_run(
            started_at=now,
            ended_at=now - timedelta(hours=1),
        ))
        assert any(e.field == "ended_at" for e in errors)

    def test_future_started_at_is_warning(self):
        future = _utcnow() + timedelta(hours=24)
        errors = validate_run(_valid_run(started_at=future))
        future_warnings = [
            e for e in errors
            if e.field == "started_at" and e.severity == "warning"
        ]
        assert len(future_warnings) == 1

    def test_unordered_turns_is_warning(self):
        turns = (
            TurnSnapshot(iteration=1, turn_type="a", input_prompt="x",
                         tokens_estimated=10, duration_ms=1.0),
            TurnSnapshot(iteration=0, turn_type="b", input_prompt="y",
                         tokens_estimated=10, duration_ms=1.0),
        )
        errors = validate_run(_valid_run(turns=turns))
        assert any("ascending" in e.message for e in errors)

    def test_negative_duration(self):
        turns = (
            TurnSnapshot(iteration=0, turn_type="a", input_prompt="x",
                         tokens_estimated=10, duration_ms=-5.0),
        )
        errors = validate_run(_valid_run(turns=turns))
        assert any("negative duration" in e.message for e in errors)

    def test_negative_tokens(self):
        turns = (
            TurnSnapshot(iteration=0, turn_type="a", input_prompt="x",
                         tokens_estimated=-10, duration_ms=5.0),
        )
        errors = validate_run(_valid_run(turns=turns))
        assert any("negative token" in e.message for e in errors)

    def test_empty_turn_type(self):
        turns = (
            TurnSnapshot(iteration=0, turn_type="", input_prompt="x",
                         tokens_estimated=10, duration_ms=5.0),
        )
        errors = validate_run(_valid_run(turns=turns))
        assert any("turn_type" in e.field and "empty" in e.message for e in errors)

    def test_negative_metric_value_for_count_unit(self):
        metrics = (Metric(name="turns_total", value=-1.0, unit="count"),)
        errors = validate_run(_valid_run(metrics=metrics))
        assert any("negative value" in e.message for e in errors)

    def test_metric_missing_name(self):
        metrics = (Metric(name="", value=1.0, unit="count"),)
        errors = validate_run(_valid_run(metrics=metrics))
        assert any("name" in e.field and "empty" in e.message for e in errors)

    def test_metric_missing_unit_is_warning(self):
        metrics = (Metric(name="custom", value=1.0, unit=""),)
        errors = validate_run(_valid_run(metrics=metrics))
        warnings = [e for e in errors if e.severity == "warning" and "unit" in e.field]
        assert len(warnings) >= 1

    def test_negative_tool_call_duration(self):
        tool_calls = (
            ToolCallRecord(
                tool_name="test_tool",
                server_name="s1",
                iteration=0,
                success=True,
                duration_ms=-10.0,
            ),
        )
        errors = validate_run(_valid_run(tool_calls=tool_calls))
        assert any("negative tool call" in e.message for e in errors)

    def test_empty_tool_name(self):
        tool_calls = (
            ToolCallRecord(
                tool_name="",
                server_name="s1",
                iteration=0,
                success=True,
                duration_ms=10.0,
            ),
        )
        errors = validate_run(_valid_run(tool_calls=tool_calls))
        assert any("tool_name" in e.field for e in errors)


# ── is_valid_run ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestIsValidRun:
    def test_valid(self):
        assert is_valid_run(_valid_run()) is True

    def test_invalid(self):
        assert is_valid_run(_valid_run(run_id="")) is False

    def test_warnings_dont_invalidate(self):
        future = _utcnow() + timedelta(hours=24)
        # Future started_at is only a warning, not an error
        # Must also set ended_at after started_at to avoid temporal error
        assert is_valid_run(_valid_run(
            started_at=future,
            ended_at=future + timedelta(seconds=5),
        )) is True


# ── validate_scenario ─────────────────────────────────────────────────


@pytest.mark.unit
class TestValidateScenario:
    def test_valid_scenario_no_errors(self):
        errors = validate_scenario(_valid_scenario())
        assert errors == []

    def test_empty_scenario_id(self):
        errors = validate_scenario(_valid_scenario(scenario_id=""))
        assert any(e.field == "scenario_id" for e in errors)

    def test_empty_name(self):
        errors = validate_scenario(_valid_scenario(name=""))
        assert any(e.field == "name" for e in errors)

    def test_empty_input_prompt(self):
        errors = validate_scenario(_valid_scenario(input_prompt=""))
        assert any(e.field == "input_prompt" for e in errors)

    def test_negative_max_turns(self):
        exp = ScenarioExpectations(max_turns=-1)
        errors = validate_scenario(_valid_scenario(expectations=exp))
        assert any("max_turns" in e.field for e in errors)

    def test_zero_max_turns(self):
        exp = ScenarioExpectations(max_turns=0)
        errors = validate_scenario(_valid_scenario(expectations=exp))
        assert any("max_turns" in e.field for e in errors)

    def test_negative_max_cost(self):
        exp = ScenarioExpectations(max_cost=-5.0)
        errors = validate_scenario(_valid_scenario(expectations=exp))
        assert any("max_cost" in e.field for e in errors)

    def test_conflicting_tool_expectations(self):
        exp = ScenarioExpectations(
            required_tool_calls=("read_file",),
            forbidden_tool_calls=("read_file",),
        )
        errors = validate_scenario(_valid_scenario(expectations=exp))
        assert any("required and forbidden" in e.message for e in errors)

    def test_valid_tool_expectations(self):
        exp = ScenarioExpectations(
            required_tool_calls=("read_file",),
            forbidden_tool_calls=("delete_file",),
        )
        errors = validate_scenario(_valid_scenario(expectations=exp))
        assert errors == []


# ── is_valid_scenario ─────────────────────────────────────────────────


@pytest.mark.unit
class TestIsValidScenario:
    def test_valid(self):
        assert is_valid_scenario(_valid_scenario()) is True

    def test_invalid(self):
        assert is_valid_scenario(_valid_scenario(name="")) is False


# ── validate_metric ───────────────────────────────────────────────────


@pytest.mark.unit
class TestValidateMetric:
    def test_valid(self):
        m = Metric(name="turns_total", value=3.0, unit="count")
        assert validate_metric(m) == []

    def test_empty_name(self):
        m = Metric(name="", value=3.0, unit="count")
        errors = validate_metric(m)
        assert any("name" in e.field for e in errors)

    def test_empty_unit_is_warning(self):
        m = Metric(name="custom", value=3.0, unit="")
        errors = validate_metric(m)
        warnings = [e for e in errors if e.severity == "warning"]
        assert len(warnings) >= 1


# ── ValidationError ───────────────────────────────────────────────────


@pytest.mark.unit
class TestValidationError:
    def test_repr(self):
        e = ValidationError("run_id", "is empty")
        assert "run_id" in repr(e)
        assert "is empty" in repr(e)

    def test_to_dict(self):
        e = ValidationError("run_id", "is empty", severity="error")
        d = e.to_dict()
        assert d["field"] == "run_id"
        assert d["message"] == "is empty"
        assert d["severity"] == "error"
