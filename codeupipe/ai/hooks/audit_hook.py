"""AuditMiddleware — Observe every filter execution for audit/observability.

Extends codeupipe's Hook to capture AuditEvents for every filter
in the pipeline. Uses fire-and-forget via AuditProducer so the agent
never blocks on audit delivery.

Usage:
    producer = LogAuditSink()
    audit_mw = AuditMiddleware(producer, session_id="abc-123")
    pipeline = build_turn_pipeline()
    pipeline.use_hook(audit_mw)
"""

from __future__ import annotations

import time
from typing import Optional

from codeupipe import Payload
from codeupipe.core.hook import Hook

from codeupipe.ai.hooks.audit_event import AuditEvent
from codeupipe.ai.hooks.audit_producer import AuditProducer


def _filter_name(f: object) -> str:
    """Extract a human-readable name from a filter or pipeline step."""
    if f is None:
        return "pipeline"
    if hasattr(f, "name"):
        return f.name
    return type(f).__name__


class AuditMiddleware(Hook):
    """Capture AuditEvents for every filter execution.

    Fires events to the producer in after() and on_error().
    """

    def __init__(self, producer: AuditProducer, session_id: str = "") -> None:
        self._producer = producer
        self._session_id = session_id
        self._start_times: dict[str, float] = {}
        self._input_snapshots: dict[str, tuple[str, ...]] = {}

    async def before(self, filter: Optional[object], payload: Payload) -> None:
        name = _filter_name(filter)
        self._start_times[name] = time.perf_counter()
        # Snapshot input keys for diff comparison
        data = payload.to_dict()
        self._input_snapshots[name] = tuple(sorted(data.keys()))

    async def after(self, filter: Optional[object], payload: Payload) -> None:
        name = _filter_name(filter)
        elapsed = time.perf_counter() - self._start_times.pop(name, 0)
        input_keys = self._input_snapshots.pop(name, ())

        # Snapshot output keys
        data = payload.to_dict()
        output_keys = tuple(sorted(data.keys()))

        # Extract loop iteration from payload
        loop_iteration = 0
        state = data.get("agent_state")
        if state and hasattr(state, "loop_iteration"):
            loop_iteration = state.loop_iteration

        session_id = self._session_id or data.get("session_id", "")

        event = AuditEvent(
            timestamp=AuditEvent.now(),
            session_id=session_id,
            loop_iteration=loop_iteration,
            link_name=name,
            input_keys=input_keys,
            output_keys=output_keys,
            duration_ms=elapsed * 1000,
        )

        await self._producer.send(event)

    async def on_error(self, filter: Optional[object], err: Exception, payload: Payload) -> None:
        name = _filter_name(filter)
        elapsed = time.perf_counter() - self._start_times.pop(name, 0)
        input_keys = self._input_snapshots.pop(name, ())

        data = payload.to_dict()
        loop_iteration = 0
        state = data.get("agent_state")
        if state and hasattr(state, "loop_iteration"):
            loop_iteration = state.loop_iteration

        session_id = self._session_id or data.get("session_id", "")

        event = AuditEvent(
            timestamp=AuditEvent.now(),
            session_id=session_id,
            loop_iteration=loop_iteration,
            link_name=name,
            input_keys=input_keys,
            output_keys=(),
            duration_ms=elapsed * 1000,
            error=str(err),
        )

        await self._producer.send(event)
