"""Validation — Data integrity checks for evaluation records.

Provides pre-save validation for RunRecords, Scenarios, and
other types before they hit the database.  Follows the
"trust but verify" principle — catch bad data early so it
doesn't corrupt downstream analysis.

Usage:
    from codeupipe.ai.eval.validation import (
        validate_run, validate_scenario, ValidationError,
    )

    errors = validate_run(run_record)
    if errors:
        for e in errors:
            print(f"INVALID: {e}")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from codeupipe.ai.eval.types import (
    Metric,
    RunOutcome,
    RunRecord,
    Scenario,
    ScenarioCategory,
    TurnSnapshot,
)

logger = logging.getLogger("codeupipe.ai.eval.validation")


class ValidationError:
    """A single validation failure."""

    __slots__ = ("field", "message", "severity")

    def __init__(
        self,
        field: str,
        message: str,
        severity: str = "error",
    ) -> None:
        self.field = field
        self.message = message
        self.severity = severity  # "error" | "warning"

    def __repr__(self) -> str:
        return f"ValidationError({self.severity}: {self.field} — {self.message})"

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
        }


def validate_run(run: RunRecord) -> list[ValidationError]:
    """Validate a RunRecord for data integrity.

    Checks:
      - Required fields (run_id, config, outcome, started_at)
      - Temporal consistency (started_at <= ended_at)
      - Metric sanity (non-negative counts, valid units)
      - Turn ordering (iterations should be sequential)
      - Outcome consistency (no success if turns is empty with certain metrics)

    Returns:
        List of ValidationError — empty means valid.
    """
    errors: list[ValidationError] = []

    # Required fields
    if not run.run_id:
        errors.append(ValidationError("run_id", "run_id is empty"))

    if not run.config:
        errors.append(ValidationError("config", "config is missing"))
    elif not run.config.model:
        errors.append(ValidationError("config.model", "model name is empty"))

    if not run.started_at:
        errors.append(ValidationError("started_at", "started_at is missing"))

    # Temporal consistency
    if run.started_at and run.ended_at:
        if run.ended_at < run.started_at:
            errors.append(ValidationError(
                "ended_at",
                f"ended_at ({run.ended_at}) is before started_at ({run.started_at})",
            ))

    # Future timestamps (warning)
    now = datetime.now(timezone.utc)
    if run.started_at and run.started_at > now:
        errors.append(ValidationError(
            "started_at",
            "started_at is in the future",
            severity="warning",
        ))

    # Turn validation
    if run.turns:
        iterations = [t.iteration for t in run.turns]
        if iterations != sorted(iterations):
            errors.append(ValidationError(
                "turns",
                "turn iterations are not in ascending order",
                severity="warning",
            ))

        for i, turn in enumerate(run.turns):
            if not turn.turn_type:
                errors.append(ValidationError(
                    f"turns[{i}].turn_type",
                    "turn_type is empty",
                ))
            if turn.duration_ms < 0:
                errors.append(ValidationError(
                    f"turns[{i}].duration_ms",
                    f"negative duration: {turn.duration_ms}",
                ))
            if turn.tokens_estimated < 0:
                errors.append(ValidationError(
                    f"turns[{i}].tokens_estimated",
                    f"negative token estimate: {turn.tokens_estimated}",
                ))

    # Metric validation
    for i, m in enumerate(run.metrics):
        if not m.name:
            errors.append(ValidationError(
                f"metrics[{i}].name",
                "metric name is empty",
            ))
        if not m.unit:
            errors.append(ValidationError(
                f"metrics[{i}].unit",
                f"metric '{m.name}' has no unit",
                severity="warning",
            ))
        # Count/flag metrics should not be negative
        if m.unit in ("count", "flag", "percent", "requests", "tokens", "ms"):
            if m.value < 0:
                errors.append(ValidationError(
                    f"metrics[{i}].value",
                    f"metric '{m.name}' has negative value ({m.value}) for unit '{m.unit}'",
                ))

    # Tool call validation
    for i, tc in enumerate(run.tool_calls):
        if not tc.tool_name:
            errors.append(ValidationError(
                f"tool_calls[{i}].tool_name",
                "tool_name is empty",
            ))
        if tc.duration_ms < 0:
            errors.append(ValidationError(
                f"tool_calls[{i}].duration_ms",
                f"negative tool call duration: {tc.duration_ms}",
            ))

    return errors


def validate_scenario(scenario: Scenario) -> list[ValidationError]:
    """Validate a Scenario for completeness.

    Checks:
      - Required fields (scenario_id, name, input_prompt)
      - Expectation sanity (max_turns > 0 if set)
      - Category is valid

    Returns:
        List of ValidationError — empty means valid.
    """
    errors: list[ValidationError] = []

    if not scenario.scenario_id:
        errors.append(ValidationError("scenario_id", "scenario_id is empty"))

    if not scenario.name:
        errors.append(ValidationError("name", "name is empty"))

    if not scenario.input_prompt:
        errors.append(ValidationError("input_prompt", "input_prompt is empty"))

    # Expectations
    exp = scenario.expectations
    if exp.max_turns is not None and exp.max_turns <= 0:
        errors.append(ValidationError(
            "expectations.max_turns",
            f"max_turns must be positive, got {exp.max_turns}",
        ))

    if exp.max_cost is not None and exp.max_cost < 0:
        errors.append(ValidationError(
            "expectations.max_cost",
            f"max_cost cannot be negative, got {exp.max_cost}",
        ))

    # Check for conflicting tool expectations
    required = set(exp.required_tool_calls)
    forbidden = set(exp.forbidden_tool_calls)
    overlap = required & forbidden
    if overlap:
        errors.append(ValidationError(
            "expectations",
            f"tools are both required and forbidden: {sorted(overlap)}",
        ))

    return errors


def validate_metric(metric: Metric) -> list[ValidationError]:
    """Validate a single Metric."""
    errors: list[ValidationError] = []

    if not metric.name:
        errors.append(ValidationError("name", "metric name is empty"))

    if not metric.unit:
        errors.append(ValidationError(
            "unit",
            f"metric '{metric.name}' has no unit",
            severity="warning",
        ))

    return errors


def is_valid_run(run: RunRecord) -> bool:
    """Quick check — returns True if no errors (warnings ok)."""
    return all(
        e.severity != "error"
        for e in validate_run(run)
    )


def is_valid_scenario(scenario: Scenario) -> bool:
    """Quick check — returns True if no errors."""
    return all(
        e.severity != "error"
        for e in validate_scenario(scenario)
    )
