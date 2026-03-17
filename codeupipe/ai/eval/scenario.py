"""Scenario management — define, load, and validate evaluation scenarios.

A scenario is the atomic unit of evaluation: one input prompt,
one set of expectations, one category.  Scenarios can be defined
in code or loaded from YAML files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    RunOutcome,
    RunRecord,
    Scenario,
    ScenarioCategory,
    ScenarioExpectations,
    _new_id,
)

logger = logging.getLogger("codeupipe.ai.eval.scenario")


# ── Scenario builders ────────────────────────────────────────────────

def build_scenario(
    name: str,
    prompt: str,
    *,
    category: ScenarioCategory = ScenarioCategory.STANDARD,
    max_turns: int | None = None,
    max_cost: float | None = None,
    required_tools: list[str] | None = None,
    forbidden_tools: list[str] | None = None,
    output_contains: list[str] | None = None,
    output_not_contains: list[str] | None = None,
    must_complete: bool = True,
    tags: list[str] | None = None,
    description: str = "",
    metadata: dict | None = None,
) -> Scenario:
    """Build a scenario from keyword arguments.

    Convenience wrapper that handles defaults and tuple conversion.
    """
    return Scenario(
        scenario_id=_new_id(),
        name=name,
        description=description or name,
        input_prompt=prompt,
        category=category,
        expectations=ScenarioExpectations(
            max_turns=max_turns,
            max_cost=max_cost,
            required_tool_calls=tuple(required_tools or []),
            forbidden_tool_calls=tuple(forbidden_tools or []),
            output_contains=tuple(output_contains or []),
            output_not_contains=tuple(output_not_contains or []),
            must_complete=must_complete,
        ),
        tags=tuple(tags or []),
        metadata=metadata or {},
    )


# ── Scenario evaluation ──────────────────────────────────────────────

def check_expectations(
    scenario: Scenario,
    run: RunRecord,
) -> list[ScenarioVerdict]:
    """Check a RunRecord against a Scenario's expectations.

    Returns a list of verdicts — one per expectation check.
    """
    verdicts: list[ScenarioVerdict] = []
    exp = scenario.expectations

    # Max turns
    if exp.max_turns is not None:
        actual = len(run.turns)
        verdicts.append(ScenarioVerdict(
            check="max_turns",
            passed=actual <= exp.max_turns,
            expected=str(exp.max_turns),
            actual=str(actual),
            detail=f"Turns: {actual} (limit: {exp.max_turns})",
        ))

    # Max cost
    if exp.max_cost is not None:
        # Find cost metric
        cost = 0.0
        for m in run.metrics:
            if m.name == "cost_premium_requests":
                cost = m.value
                break
        verdicts.append(ScenarioVerdict(
            check="max_cost",
            passed=cost <= exp.max_cost,
            expected=str(exp.max_cost),
            actual=str(cost),
            detail=f"Cost: {cost} premium requests (limit: {exp.max_cost})",
        ))

    # Required tool calls
    tool_names_used = {tc.tool_name for tc in run.tool_calls}
    for tool in exp.required_tool_calls:
        verdicts.append(ScenarioVerdict(
            check="required_tool",
            passed=tool in tool_names_used,
            expected=tool,
            actual=str(tool_names_used),
            detail=f"Required tool '{tool}' {'found' if tool in tool_names_used else 'MISSING'}",
        ))

    # Forbidden tool calls
    for tool in exp.forbidden_tool_calls:
        verdicts.append(ScenarioVerdict(
            check="forbidden_tool",
            passed=tool not in tool_names_used,
            expected=f"NOT {tool}",
            actual=str(tool_names_used),
            detail=f"Forbidden tool '{tool}' {'not used' if tool not in tool_names_used else 'WAS USED'}",
        ))

    # Output contains
    all_responses = " ".join(
        t.response_content or "" for t in run.turns
    ).lower()
    for phrase in exp.output_contains:
        verdicts.append(ScenarioVerdict(
            check="output_contains",
            passed=phrase.lower() in all_responses,
            expected=phrase,
            actual=all_responses[:200],
            detail=f"Output {'contains' if phrase.lower() in all_responses else 'MISSING'} '{phrase}'",
        ))

    # Output not contains
    for phrase in exp.output_not_contains:
        verdicts.append(ScenarioVerdict(
            check="output_not_contains",
            passed=phrase.lower() not in all_responses,
            expected=f"NOT '{phrase}'",
            actual=all_responses[:200],
            detail=f"Forbidden phrase '{phrase}' {'absent' if phrase.lower() not in all_responses else 'FOUND'}",
        ))

    # Must complete (done naturally, not max_iterations)
    if exp.must_complete:
        verdicts.append(ScenarioVerdict(
            check="must_complete",
            passed=run.outcome == RunOutcome.SUCCESS,
            expected="success",
            actual=str(run.outcome),
            detail=f"Outcome: {run.outcome}",
        ))

    return verdicts


# ── Scenario loading from files ───────────────────────────────────────

def load_scenarios_from_json(path: str | Path) -> list[Scenario]:
    """Load scenarios from a JSON file.

    Expected format:
    [
        {
            "name": "...",
            "prompt": "...",
            "category": "standard",
            "expectations": { ... },
            "tags": [...]
        },
        ...
    ]
    """
    path = Path(path)
    if not path.exists():
        logger.warning("Scenario file not found: %s", path)
        return []

    with path.open() as f:
        data = json.load(f)

    scenarios = []
    for item in data:
        exp_data = item.get("expectations", {})
        scenarios.append(Scenario(
            scenario_id=item.get("scenario_id", _new_id()),
            name=item.get("name", ""),
            description=item.get("description", item.get("name", "")),
            input_prompt=item.get("prompt", item.get("input_prompt", "")),
            category=ScenarioCategory(item.get("category", "standard")),
            expectations=ScenarioExpectations(
                max_turns=exp_data.get("max_turns"),
                max_cost=exp_data.get("max_cost"),
                required_tool_calls=tuple(exp_data.get("required_tool_calls", [])),
                forbidden_tool_calls=tuple(exp_data.get("forbidden_tool_calls", [])),
                output_contains=tuple(exp_data.get("output_contains", [])),
                output_not_contains=tuple(exp_data.get("output_not_contains", [])),
                must_complete=exp_data.get("must_complete", True),
                custom=exp_data.get("custom", {}),
            ),
            tags=tuple(item.get("tags", [])),
            metadata=item.get("metadata", {}),
        ))

    logger.debug("Loaded %d scenarios from %s", len(scenarios), path)
    return scenarios


def save_scenarios_to_json(scenarios: list[Scenario], path: str | Path) -> None:
    """Save scenarios to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = []
    for s in scenarios:
        item = s.to_dict()
        # Rename for file format consistency
        item["prompt"] = item.pop("input_prompt")
        data.append(item)

    with path.open("w") as f:
        json.dump(data, f, indent=2)

    logger.debug("Saved %d scenarios to %s", len(scenarios), path)


# ── Verdict ───────────────────────────────────────────────────────────

class ScenarioVerdict:
    """Result of checking one expectation against a run."""

    __slots__ = ("check", "passed", "expected", "actual", "detail")

    def __init__(
        self,
        check: str,
        passed: bool,
        expected: str = "",
        actual: str = "",
        detail: str = "",
    ) -> None:
        self.check = check
        self.passed = passed
        self.expected = expected
        self.actual = actual
        self.detail = detail

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"ScenarioVerdict({status}: {self.check} — {self.detail})"
