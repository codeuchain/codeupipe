"""AgentState — Persistent state across loop iterations.

Tracks what the agent has done, what's active, and whether it's done.
Immutable — each mutation returns a new instance to align with
codeupipe's Context immutability pattern.

TurnRecord captures what happened in a single turn for observability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from codeupipe.ai._compat import StrEnum


class TurnType(StrEnum):
    """What kind of input triggered this turn."""

    USER_PROMPT = "user_prompt"
    FOLLOW_UP = "follow_up"
    NOTIFICATION = "notification"
    TOOL_CONTINUATION = "tool_continuation"


@dataclass(frozen=True)
class TurnRecord:
    """Immutable record of a single agent turn.

    Attributes:
        iteration: Which loop iteration produced this turn.
        turn_type: What triggered the turn (user prompt, follow-up, notification).
        input_prompt: The prompt sent to the agent.
        response_content: The agent's text response (if any).
        tool_calls_count: How many tool calls the SDK executed during this turn.
        timestamp: When this turn started.
    """

    iteration: int
    turn_type: TurnType
    input_prompt: str
    response_content: str | None = None
    tool_calls_count: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class AgentState:
    """Persistent state across loop iterations.

    Frozen dataclass — every mutation returns a new instance.
    This aligns with Context's immutable insert pattern.

    Attributes:
        loop_iteration: Current iteration count (0-based, incremented after each turn).
        done: Whether the agent has signaled completion.
        max_iterations: Safety cap to prevent infinite loops.
        turn_history: Ordered list of TurnRecords for observability.
        active_capabilities: Names of capabilities currently loaded into context.
    """

    loop_iteration: int = 0
    done: bool = False
    max_iterations: int = 10
    turn_history: tuple[TurnRecord, ...] = ()
    active_capabilities: tuple[str, ...] = ()

    # ── Mutations (return new instances) ──────────────────────────────

    def increment(self) -> AgentState:
        """Advance the loop iteration counter."""
        return AgentState(
            loop_iteration=self.loop_iteration + 1,
            done=self.done,
            max_iterations=self.max_iterations,
            turn_history=self.turn_history,
            active_capabilities=self.active_capabilities,
        )

    def mark_done(self) -> AgentState:
        """Signal that the agent has completed its task."""
        return AgentState(
            loop_iteration=self.loop_iteration,
            done=True,
            max_iterations=self.max_iterations,
            turn_history=self.turn_history,
            active_capabilities=self.active_capabilities,
        )

    def record_turn(self, turn: TurnRecord) -> AgentState:
        """Append a turn record to history."""
        return AgentState(
            loop_iteration=self.loop_iteration,
            done=self.done,
            max_iterations=self.max_iterations,
            turn_history=self.turn_history + (turn,),
            active_capabilities=self.active_capabilities,
        )

    def add_capability(self, name: str) -> AgentState:
        """Track an adopted capability."""
        if name in self.active_capabilities:
            return self
        return AgentState(
            loop_iteration=self.loop_iteration,
            done=self.done,
            max_iterations=self.max_iterations,
            turn_history=self.turn_history,
            active_capabilities=self.active_capabilities + (name,),
        )

    def remove_capability(self, name: str) -> AgentState:
        """Drop an adopted capability."""
        return AgentState(
            loop_iteration=self.loop_iteration,
            done=self.done,
            max_iterations=self.max_iterations,
            turn_history=self.turn_history,
            active_capabilities=tuple(
                c for c in self.active_capabilities if c != name
            ),
        )

    # ── Queries ───────────────────────────────────────────────────────

    @property
    def should_continue(self) -> bool:
        """Whether the loop should run another iteration."""
        return not self.done and self.loop_iteration < self.max_iterations

    @property
    def is_first_turn(self) -> bool:
        """Whether this is the first iteration (initial user prompt)."""
        return self.loop_iteration == 0

    @property
    def hit_max_iterations(self) -> bool:
        """Whether the loop was stopped by the safety cap."""
        return self.loop_iteration >= self.max_iterations and not self.done
