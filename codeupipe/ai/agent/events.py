"""AgentEvent and EventType — the SDK's typed event protocol.

AgentEvent is the single data object that flows from the agent to
any consumer (CLI, TUI, web, programmatic). Every UI receives the
same stream of AgentEvents — adaptors decide how to render them.

EventType is a discriminated enum for the kinds of events the agent
emits. Events are split into two tiers:
  - Default: TURN_START, TURN_END, RESPONSE, DONE, ERROR
  - Verbose: TOOL_CALL, TOOL_RESULT, NOTIFICATION, STATE_CHANGE

Consumers opt into verbose events via AgentConfig.verbose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class EventType(StrEnum):
    """Kinds of events the agent emits."""

    TURN_START = "turn_start"
    TURN_END = "turn_end"
    RESPONSE = "response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    NOTIFICATION = "notification"
    STATE_CHANGE = "state_change"
    BILLING = "billing"
    ERROR = "error"
    DONE = "done"


# Event types that require verbose=True to be yielded
_VERBOSE_TYPES: frozenset[EventType] = frozenset({
    EventType.TOOL_CALL,
    EventType.TOOL_RESULT,
    EventType.NOTIFICATION,
    EventType.STATE_CHANGE,
    EventType.BILLING,
})


@dataclass(frozen=True)
class AgentEvent:
    """Immutable event emitted by the agent during execution.

    Attributes:
        type: What kind of event this is.
        data: Payload dict (varies by event type).
        timestamp: When this event was created (UTC).
        iteration: Which loop iteration produced this event.
        source: Which component emitted this event.
    """

    type: EventType
    data: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    iteration: int = 0
    source: str = "agent"

    @property
    def is_verbose(self) -> bool:
        """Whether this event is verbose (detail-level, not default)."""
        return self.type in _VERBOSE_TYPES

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON/SSE transport."""
        return {
            "type": str(self.type),
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "iteration": self.iteration,
            "source": self.source,
        }

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict())
