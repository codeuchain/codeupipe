"""EvalCollector — Mass data capture for the evaluation framework.

Capture-everything philosophy: record every event, every measurement,
every piece of raw data that flows through the agent.  Filter later.

Integrates with the existing agent infrastructure:
  - Implements AuditProducer so it plugs into CompositeAuditProducer
  - Accepts AgentEvents from the SDK event stream
  - Accepts raw dicts for anything else

All data is persisted immediately to the EvalStore.  Nothing is
buffered in memory beyond what's needed for the current run.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from codeupipe.ai.eval.metrics import compute_all
from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    Metric,
    RawEvent,
    RunConfig,
    RunOutcome,
    RunRecord,
    ToolCallRecord,
    TurnSnapshot,
    _new_id,
    _utcnow,
)

logger = logging.getLogger("codeupipe.ai.eval.collector")


class EvalCollector:
    """Mass data collector — captures everything about an agent run.

    Plugs into the existing audit pipeline as an AuditProducer and
    into the SDK event stream for complete coverage.

    Usage:
        store = EvalStore("eval.db")
        collector = EvalCollector(store)

        # Start recording a run
        collector.begin_run(config=RunConfig(model="gpt-4.1"))

        # Wire into audit pipeline
        composite = CompositeAuditProducer([LogAuditSink(), collector])

        # Record SDK events
        async for event in agent.run("..."):
            collector.record_event(event)

        # Finalize
        run = collector.end_run(outcome=RunOutcome.SUCCESS)
    """

    def __init__(self, store: EvalStore) -> None:
        self._store = store
        self._run_id: str = ""
        self._session_id: str = ""
        self._scenario_id: str | None = None
        self._experiment_id: str | None = None
        self._config: RunConfig = RunConfig()
        self._started_at: datetime | None = None
        self._turns: list[TurnSnapshot] = []
        self._tool_calls: list[ToolCallRecord] = []
        self._audit_events: list[dict] = []
        self._raw_data: dict = {}
        self._counters: dict[str, int] = {}
        self._active = False

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def is_active(self) -> bool:
        return self._active

    # ── Run lifecycle ─────────────────────────────────────────────────

    def begin_run(
        self,
        *,
        config: RunConfig | None = None,
        session_id: str = "",
        scenario_id: str | None = None,
        experiment_id: str | None = None,
        run_id: str | None = None,
    ) -> str:
        """Start recording a new run.  Returns the run_id."""
        self._run_id = run_id or _new_id()
        self._session_id = session_id
        self._scenario_id = scenario_id
        self._experiment_id = experiment_id
        self._config = config or RunConfig()
        self._started_at = _utcnow()
        self._turns = []
        self._tool_calls = []
        self._audit_events = []
        self._raw_data = {}
        self._counters = {}
        self._active = True

        # Insert a placeholder run so raw_events FK is satisfied
        placeholder = RunRecord(
            run_id=self._run_id,
            session_id=self._session_id,
            scenario_id=self._scenario_id,
            experiment_id=self._experiment_id,
            config=self._config,
            started_at=self._started_at,
            outcome=RunOutcome.UNKNOWN,
        )
        self._store.save_run(placeholder)

        logger.debug("Run started: %s", self._run_id)
        return self._run_id

    def end_run(
        self,
        outcome: RunOutcome = RunOutcome.UNKNOWN,
    ) -> RunRecord:
        """Finalize the run — compute metrics, persist, and return the record."""
        if not self._active:
            raise RuntimeError("No active run to end")

        ended_at = _utcnow()

        # Build the run record without metrics first
        run = RunRecord(
            run_id=self._run_id,
            session_id=self._session_id,
            scenario_id=self._scenario_id,
            experiment_id=self._experiment_id,
            config=self._config,
            started_at=self._started_at or ended_at,
            ended_at=ended_at,
            outcome=outcome,
            turns=tuple(self._turns),
            tool_calls=tuple(self._tool_calls),
            metrics=(),  # computed below
            audit_events=tuple(self._audit_events),
            raw_data=dict(self._raw_data),
        )

        # Compute all registered metrics
        computed_metrics = compute_all(run)

        # Rebuild with metrics
        run = RunRecord(
            run_id=run.run_id,
            session_id=run.session_id,
            scenario_id=run.scenario_id,
            experiment_id=run.experiment_id,
            config=run.config,
            started_at=run.started_at,
            ended_at=run.ended_at,
            outcome=run.outcome,
            turns=run.turns,
            tool_calls=run.tool_calls,
            metrics=tuple(computed_metrics),
            audit_events=run.audit_events,
            raw_data=run.raw_data,
        )

        # Persist everything
        self._store.save_run(run)

        logger.debug(
            "Run ended: %s — %s (%d turns, %d metrics, %d raw events)",
            self._run_id, outcome, len(run.turns),
            len(run.metrics), len(run.audit_events),
        )

        self._active = False
        return run

    # ── Data recording ────────────────────────────────────────────────

    def record_turn(self, turn: TurnSnapshot) -> None:
        """Record a turn snapshot."""
        if not self._active:
            return
        self._turns.append(turn)

        # Also store as raw event for the everything-table
        self._store.save_raw_event(RawEvent(
            run_id=self._run_id,
            event_type="turn",
            payload=turn.to_dict(),
        ))

    def record_tool_call(self, tool_call: ToolCallRecord) -> None:
        """Record a tool call."""
        if not self._active:
            return
        self._tool_calls.append(tool_call)

        self._store.save_raw_event(RawEvent(
            run_id=self._run_id,
            event_type="tool_call",
            payload=tool_call.to_dict(),
        ))

    def record_raw(self, event_type: str, payload: dict) -> None:
        """Record any raw event — the catch-all.

        This is the "grab everything" method.  Pass in whatever
        you have and we'll store it.
        """
        if not self._active:
            return
        self._store.save_raw_event(RawEvent(
            run_id=self._run_id,
            event_type=event_type,
            payload=payload,
        ))

    def increment(self, counter_name: str, amount: int = 1) -> None:
        """Increment a named counter in raw_data.

        Use for tracking things like intent_shifts, discoveries_triggered,
        etc. without needing a typed field.
        """
        if not self._active:
            return
        current = self._raw_data.get(counter_name, 0)
        self._raw_data[counter_name] = current + amount

    def set_raw(self, key: str, value: object) -> None:
        """Set an arbitrary key in raw_data."""
        if not self._active:
            return
        self._raw_data[key] = value

    # ── AuditProducer interface ───────────────────────────────────────

    async def send(self, event: object) -> None:
        """Accept an AuditEvent — implements AuditProducer.send().

        By duck-typing on ``to_dict()``, this works with AuditEvent
        without importing it (avoids circular dependency with
        codeupipe.ai.hooks).
        """
        if not self._active:
            return
        try:
            event_dict = event.to_dict() if hasattr(event, "to_dict") else {}
            self._audit_events.append(event_dict)

            self._store.save_raw_event(RawEvent(
                run_id=self._run_id,
                event_type="audit",
                payload=event_dict,
            ))
        except Exception:  # noqa: BLE001
            pass  # fire and forget — never block the agent

    async def flush(self) -> None:
        """Flush (no-op — we persist immediately)."""

    async def close(self) -> None:
        """Close the collector."""

    # ── SDK AgentEvent recording ──────────────────────────────────────

    def record_agent_event(self, event: object) -> None:
        """Record an AgentEvent from the SDK.

        Duck-types on to_dict() to avoid importing codeupipe.ai.agent.
        Automatically extracts turns, tool calls, and billing from
        the event stream.
        """
        if not self._active:
            return

        event_dict = event.to_dict() if hasattr(event, "to_dict") else {}
        event_type = getattr(event, "type", str(event_dict.get("type", "")))

        # Always store the raw event
        self._store.save_raw_event(RawEvent(
            run_id=self._run_id,
            event_type=f"sdk_{event_type}",
            payload=event_dict,
        ))

        # Extract structured data from known event types
        data = getattr(event, "data", event_dict.get("data", {}))
        iteration = getattr(event, "iteration", event_dict.get("iteration", 0))

        if str(event_type) == "response":
            self.record_turn(TurnSnapshot(
                iteration=iteration,
                turn_type=data.get("turn_type", "user_prompt"),
                input_prompt=data.get("input_prompt", ""),
                response_content=data.get("content", ""),
                tool_calls_count=data.get("tool_calls_count", 0),
                tokens_estimated=data.get("tokens_estimated", 0),
                model_used=data.get("model", self._config.model),
            ))

        elif str(event_type) == "tool_call":
            self.record_tool_call(ToolCallRecord(
                iteration=iteration,
                tool_name=data.get("tool_name", ""),
                server_name=data.get("server_name", ""),
                arguments=data.get("arguments", {}),
            ))

        elif str(event_type) == "tool_result":
            # Update last tool call with result
            if self._tool_calls:
                last = self._tool_calls[-1]
                self._tool_calls[-1] = ToolCallRecord(
                    iteration=last.iteration,
                    tool_name=last.tool_name,
                    server_name=last.server_name,
                    arguments=last.arguments,
                    result_summary=str(data.get("result", ""))[:500],
                    duration_ms=data.get("duration_ms", 0.0),
                    success=data.get("success", True),
                    timestamp=last.timestamp,
                    raw_data=data,
                )

        elif str(event_type) == "billing":
            self.set_raw("last_billing", data)
            self.increment("billing_events")

        elif str(event_type) == "notification":
            self.increment("notifications_received")

        elif str(event_type) == "state_change":
            action = data.get("action", "")
            if action == "intent_shifted":
                self.increment("intent_shifts")
            elif action == "capability_adopted":
                self.increment("capabilities_adopted")
            elif action == "capability_dropped":
                self.increment("capabilities_dropped")
            elif action == "rediscovered":
                self.increment("discoveries_triggered")
