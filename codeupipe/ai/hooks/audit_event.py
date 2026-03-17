"""AuditEvent — Structured audit record for observability.

Every Link execution generates an AuditEvent capturing:
  - What ran (link_name)
  - When (timestamp)
  - Where in the loop (session_id, loop_iteration)
  - What data flowed (input_keys → output_keys)
  - How long (duration_ms)
  - What went wrong (error)
  - Extra context (metadata)

Frozen dataclass — immutable once created, safe for async transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class AuditEvent:
    """Immutable audit record for a single Link execution."""

    timestamp: datetime
    session_id: str
    loop_iteration: int
    link_name: str
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]
    duration_ms: float
    error: str | None = None
    metadata: dict | None = None

    @staticmethod
    def now() -> datetime:
        """UTC timestamp for audit events."""
        return datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        """Serialize to plain dict for transport."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "loop_iteration": self.loop_iteration,
            "link_name": self.link_name,
            "input_keys": list(self.input_keys),
            "output_keys": list(self.output_keys),
            "duration_ms": self.duration_ms,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ContextAttribution:
    """Token usage attribution by source.

    Tracks how much of the context budget is consumed by each
    source: turns, tools, notifications, system, capabilities, etc.
    """

    source: str
    estimated_tokens: int
    percentage: float = 0.0
    item_count: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to plain dict."""
        return {
            "source": self.source,
            "estimated_tokens": self.estimated_tokens,
            "percentage": self.percentage,
            "item_count": self.item_count,
            "metadata": self.metadata,
        }
