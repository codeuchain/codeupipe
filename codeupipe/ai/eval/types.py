"""Core data types for the evaluation framework.

Frozen dataclasses — every evaluation artifact is immutable once
created.  This matches the pattern used throughout codeupipe.ai
(AgentState, TurnRecord, AuditEvent, ContextEntry).

Capture-everything philosophy: raw_data dicts on key types allow
storing any data we haven't formally typed yet.  Filter later.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


# ── Helpers ───────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ── Enums ─────────────────────────────────────────────────────────────

class RunOutcome(StrEnum):
    """How an agent run ended."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ERROR = "error"
    UNKNOWN = "unknown"


class ScenarioCategory(StrEnum):
    """Classification of evaluation scenarios."""

    STANDARD = "standard"
    EDGE_CASE = "edge_case"
    ADVERSARIAL = "adversarial"
    MULTI_TURN = "multi_turn"
    COST_CONSTRAINED = "cost_constrained"


class ExperimentStatus(StrEnum):
    """Lifecycle state of an experiment."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Run Configuration ────────────────────────────────────────────────

@dataclass(frozen=True)
class RunConfig:
    """Snapshot of every tunable knob for reproducibility.

    Anything that can affect agent behavior belongs here.
    The ``extra`` dict is the escape hatch for variables we
    haven't formalized yet — capture now, type later.
    """

    model: str = "gpt-4.1"
    max_iterations: int = 10
    context_budget: int = 128_000
    directives: tuple[str, ...] = ()
    discovery_top_k: int = 5
    similarity_threshold: float = 0.7
    embedding_model: str = "Snowflake/snowflake-arctic-embed-m-v2.0"
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "max_iterations": self.max_iterations,
            "context_budget": self.context_budget,
            "directives": list(self.directives),
            "discovery_top_k": self.discovery_top_k,
            "similarity_threshold": self.similarity_threshold,
            "embedding_model": self.embedding_model,
            "extra": self.extra,
        }


# ── Turn Snapshot ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class TurnSnapshot:
    """Full capture of a single agent turn.

    Goes beyond ``TurnRecord`` by including tokens, duration,
    model used, and a raw_data escape hatch.
    """

    iteration: int
    turn_type: str
    input_prompt: str
    response_content: str | None = None
    tool_calls_count: int = 0
    tokens_estimated: int = 0
    duration_ms: float = 0.0
    model_used: str = ""
    timestamp: datetime = field(default_factory=_utcnow)
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "turn_type": self.turn_type,
            "input_prompt": self.input_prompt,
            "response_content": self.response_content,
            "tool_calls_count": self.tool_calls_count,
            "tokens_estimated": self.tokens_estimated,
            "duration_ms": self.duration_ms,
            "model_used": self.model_used,
            "timestamp": self.timestamp.isoformat(),
            "raw_data": self.raw_data,
        }


# ── Tool Call Record ──────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolCallRecord:
    """Record of a single tool invocation."""

    iteration: int
    tool_name: str
    server_name: str = ""
    arguments: dict = field(default_factory=dict)
    result_summary: str = ""
    duration_ms: float = 0.0
    success: bool = True
    timestamp: datetime = field(default_factory=_utcnow)
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "tool_name": self.tool_name,
            "server_name": self.server_name,
            "arguments": self.arguments,
            "result_summary": self.result_summary,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "raw_data": self.raw_data,
        }


# ── Metric ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Metric:
    """A single named measurement.

    Tags enable slicing and grouping.  The raw_data escape hatch
    stores anything that contributed to this metric's value.
    """

    name: str
    value: float
    unit: str = ""
    tags: tuple[str, ...] = ()
    timestamp: datetime = field(default_factory=_utcnow)
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "tags": list(self.tags),
            "timestamp": self.timestamp.isoformat(),
            "raw_data": self.raw_data,
        }


# ── Run Record ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RunRecord:
    """Complete record of one agent execution.

    This is the master artifact: every turn, every tool call,
    every metric, every raw event.  Nothing is discarded.
    """

    run_id: str = field(default_factory=_new_id)
    session_id: str = ""
    scenario_id: str | None = None
    experiment_id: str | None = None
    config: RunConfig = field(default_factory=RunConfig)
    started_at: datetime = field(default_factory=_utcnow)
    ended_at: datetime | None = None
    outcome: RunOutcome = RunOutcome.UNKNOWN
    turns: tuple[TurnSnapshot, ...] = ()
    tool_calls: tuple[ToolCallRecord, ...] = ()
    metrics: tuple[Metric, ...] = ()
    audit_events: tuple[dict, ...] = ()
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "scenario_id": self.scenario_id,
            "experiment_id": self.experiment_id,
            "config": self.config.to_dict(),
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "outcome": str(self.outcome),
            "turns": [t.to_dict() for t in self.turns],
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "metrics": [m.to_dict() for m in self.metrics],
            "audit_events": list(self.audit_events),
            "raw_data": self.raw_data,
        }


# ── Scenario ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScenarioExpectations:
    """What we expect from a successful run against a scenario.

    Every field is optional — only set what you want to assert.
    """

    max_turns: int | None = None
    max_cost: float | None = None
    required_tool_calls: tuple[str, ...] = ()
    forbidden_tool_calls: tuple[str, ...] = ()
    output_contains: tuple[str, ...] = ()
    output_not_contains: tuple[str, ...] = ()
    must_complete: bool = True
    custom: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "max_turns": self.max_turns,
            "max_cost": self.max_cost,
            "required_tool_calls": list(self.required_tool_calls),
            "forbidden_tool_calls": list(self.forbidden_tool_calls),
            "output_contains": list(self.output_contains),
            "output_not_contains": list(self.output_not_contains),
            "must_complete": self.must_complete,
            "custom": self.custom,
        }


@dataclass(frozen=True)
class Scenario:
    """A defined evaluation scenario — input + expectations."""

    scenario_id: str = field(default_factory=_new_id)
    name: str = ""
    description: str = ""
    input_prompt: str = ""
    category: ScenarioCategory = ScenarioCategory.STANDARD
    expectations: ScenarioExpectations = field(default_factory=ScenarioExpectations)
    tags: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "input_prompt": self.input_prompt,
            "category": str(self.category),
            "expectations": self.expectations.to_dict(),
            "tags": list(self.tags),
            "metadata": self.metadata,
        }


# ── Baseline ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Baseline:
    """A saved control — aggregated metrics from N runs.

    Use as the reference point for all future comparisons.
    """

    baseline_id: str = field(default_factory=_new_id)
    name: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    config: RunConfig = field(default_factory=RunConfig)
    metrics: dict = field(default_factory=dict)  # metric_name → aggregated value
    run_count: int = 0
    run_ids: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "baseline_id": self.baseline_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "config": self.config.to_dict(),
            "metrics": self.metrics,
            "run_count": self.run_count,
            "run_ids": list(self.run_ids),
            "metadata": self.metadata,
        }


# ── Experiment ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Experiment:
    """An A/B comparison — multiple configs × multiple scenarios.

    Links runs to configs and scenarios for structured comparison.
    """

    experiment_id: str = field(default_factory=_new_id)
    name: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    configs: tuple[RunConfig, ...] = ()
    scenario_ids: tuple[str, ...] = ()
    status: ExperimentStatus = ExperimentStatus.PENDING
    baseline_id: str | None = None
    run_ids: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "configs": [c.to_dict() for c in self.configs],
            "scenario_ids": list(self.scenario_ids),
            "status": str(self.status),
            "baseline_id": self.baseline_id,
            "run_ids": list(self.run_ids),
            "metadata": self.metadata,
        }


# ── Raw Event ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RawEvent:
    """Any event we capture — typed or untyped.

    This is the "grab everything" table.  Every AuditEvent,
    AgentEvent, notification, system metric, or anything else
    gets stored here with minimal structure.
    """

    event_id: str = field(default_factory=_new_id)
    run_id: str = ""
    event_type: str = ""
    timestamp: datetime = field(default_factory=_utcnow)
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
        }
