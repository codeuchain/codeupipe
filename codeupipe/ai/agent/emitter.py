"""EventEmitterMiddleware — translates filter execution into AgentEvents.

This Hook sits on the agent's turn pipeline and intercepts every
filter's before/after/on_error callbacks.  It maps specific filter
completions to typed AgentEvent objects and pushes them into an
asyncio.Queue that the Agent.run() generator drains.

Zero changes to existing filters — this is pure observation.

codeupipe Hook interface (actual signatures):
    before(self, filter: Optional[Filter], payload: Payload)
    after(self, filter: Optional[Filter], payload: Payload)
    on_error(self, filter: Optional[Filter], error: Exception, payload: Payload)

Filter names are resolved from class names by convention:
    ReadInputLink  →  read_input
    CheckDoneLink  →  check_done

Emits:
    read_input (after)           → TURN_START
    process_response (after)     → TURN_END + RESPONSE
    inject_notifications (after) → NOTIFICATION (one per notification)
    check_done (after)           → DONE (when state.done)
    manage_state (after)         → STATE_CHANGE (when updates exist)
    any filter (on_error)        → ERROR
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

from codeupipe import Payload
from codeupipe.core.filter import Filter
from codeupipe.core.hook import Hook

from codeupipe.ai.agent.billing import UsageTracker, get_multiplier
from codeupipe.ai.agent.events import AgentEvent, EventType


class EventEmitterMiddleware(Hook):
    """Observe filter execution and emit AgentEvents to a queue.

    Args:
        queue: asyncio.Queue to push AgentEvents into.
        model: Language model name for billing tracking.
    """

    def __init__(self, queue: asyncio.Queue[AgentEvent], model: str = "gpt-4.1") -> None:
        self._queue = queue
        self._usage = UsageTracker(model=model)

    # ── Hook interface ───────────────────────────────────────────────

    async def before(self, filter: Optional[Filter], payload: Payload) -> None:  # type: ignore[override]
        # No events emitted on before — we wait for completion
        pass

    async def after(self, filter: Optional[Filter], payload: Payload) -> None:  # type: ignore[override]
        if filter is None:
            return  # Pipeline-level call (start/end), skip

        name = self._resolve_filter_name(filter)
        iteration = self._get_iteration(payload)

        if name == "read_input":
            await self._on_read_input(payload, iteration)
        elif name == "process_response":
            await self._on_process_response(payload, iteration)
        elif name in ("language_model", "send_turn"):
            await self._on_send_turn(payload, iteration)
        elif name == "inject_notifications":
            await self._on_inject_notifications(payload, iteration)
        elif name == "check_done":
            await self._on_check_done(payload, iteration)
        elif name == "manage_state":
            await self._on_manage_state(payload, iteration)

    async def on_error(self, filter: Optional[Filter], error: Exception, payload: Payload) -> None:  # type: ignore[override]
        if not hasattr(payload, "get"):
            iteration = 0
        else:
            iteration = self._get_iteration(payload)

        filter_name = self._resolve_filter_name(filter) or "pipeline"
        await self._emit(AgentEvent(
            type=EventType.ERROR,
            data={"error": str(error), "filter": filter_name},
            iteration=iteration,
            source=filter_name,
        ))

    # ── Filter-specific handlers ─────────────────────────────────────

    async def _on_read_input(self, payload: Payload, iteration: int) -> None:
        prompt = payload.get("next_prompt")
        if prompt is None:
            return  # No prompt prepared — CheckDoneLink will handle

        await self._emit(AgentEvent(
            type=EventType.TURN_START,
            data={"prompt": prompt, "iteration": iteration},
            iteration=iteration,
            source="read_input",
        ))

    async def _on_process_response(self, payload: Payload, iteration: int) -> None:
        response = payload.get("response")

        await self._emit(AgentEvent(
            type=EventType.TURN_END,
            data={"response": response, "iteration": iteration},
            iteration=iteration,
            source="process_response",
        ))

        if response is not None:
            await self._emit(AgentEvent(
                type=EventType.RESPONSE,
                data={"content": response},
                iteration=iteration,
                source="process_response",
            ))

    async def _on_send_turn(self, payload: Payload, iteration: int) -> None:
        """Emit BILLING event after language_model if a prompt was actually sent."""
        next_prompt = payload.get("next_prompt")
        response = payload.get("response")

        # Only bill if a prompt was sent and a response received
        if next_prompt is None or response is None:
            return

        self._usage.record_turn()

        await self._emit(AgentEvent(
            type=EventType.BILLING,
            data={
                "model": self._usage.model,
                "multiplier": self._usage.multiplier,
                "premium_requests": self._usage.multiplier,
                "total_requests": self._usage.total_requests,
                "total_premium_requests": self._usage.total_premium_requests,
            },
            iteration=iteration,
            source="language_model",
        ))

    async def _on_inject_notifications(self, payload: Payload, iteration: int) -> None:
        notifications = payload.get("pending_notifications") or []
        for notif in notifications:
            if isinstance(notif, dict):
                await self._emit(AgentEvent(
                    type=EventType.NOTIFICATION,
                    data=notif,
                    iteration=iteration,
                    source="inject_notifications",
                ))

    async def _on_check_done(self, payload: Payload, iteration: int) -> None:
        state = payload.get("agent_state")
        if state is None or not getattr(state, "done", False):
            return

        response = payload.get("response")
        await self._emit(AgentEvent(
            type=EventType.DONE,
            data={
                "final_response": response,
                "total_iterations": iteration,
                "reason": "max_iterations" if getattr(state, "hit_max_iterations", False) else "complete",
            },
            iteration=iteration,
            source="check_done",
        ))

    async def _on_manage_state(self, payload: Payload, iteration: int) -> None:
        updates = payload.get("state_updates")
        if not updates:
            return

        await self._emit(AgentEvent(
            type=EventType.STATE_CHANGE,
            data=updates if isinstance(updates, dict) else {"updates": updates},
            iteration=iteration,
            source="manage_state",
        ))

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_filter_name(filter: Any) -> str | None:
        """Derive the registered filter name from a Filter object.

        Convention: CamelCase class name → snake_case, strip '_link' suffix.
            ReadInputLink  → read_input
            CheckDoneLink  → check_done
        """
        if filter is None:
            return None
        class_name = type(filter).__name__
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
        if snake.endswith("_link"):
            snake = snake[:-5]
        return snake

    def _get_iteration(self, payload: Payload) -> int:
        """Extract current iteration from agent_state, defaulting to 0."""
        state = payload.get("agent_state")
        if state is None:
            return 0
        return getattr(state, "loop_iteration", 0)

    async def _emit(self, event: AgentEvent) -> None:
        """Push an event into the queue."""
        await self._queue.put(event)
