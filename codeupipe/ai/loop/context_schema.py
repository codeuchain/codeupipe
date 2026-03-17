"""ContextEntry — Typed, attributable, sortable context schema.

Every piece of information in the agent's context window is
represented as a ContextEntry. This replaces ad-hoc dict keys
with a formal, versioned schema that enables:

  - Zone-based positioning (foundational → contextual → focal)
  - Importance-weighted decay and pruning
  - Token budget enforcement per zone
  - Audit trail of what's in the context window

Zones follow the positional bias pattern:
  - FOUNDATIONAL (beginning) — system identity, directives
  - CONTEXTUAL (middle) — conversation history, tool results
  - FOCAL (end) — current task, latest notifications
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Zone(IntEnum):
    """Context positioning zones.

    Ordered by position in the assembled context:
    FOUNDATIONAL first, FOCAL last.
    """

    FOUNDATIONAL = 0  # System identity, directives — beginning
    CONTEXTUAL = 1    # History, tool results — middle
    FOCAL = 2         # Current task, recent notifications — end


@dataclass(frozen=True)
class ContextEntry:
    """A single piece of context in the agent's window.

    Immutable — once created, entries don't change. New entries
    replace old ones when content is updated.

    Attributes:
        zone: Where this entry should be positioned.
        source: What produced this entry (e.g. "directive", "user_prompt").
        content: The actual text content.
        importance: Relative importance (0.0–1.0). Higher = harder to prune.
        token_estimate: Estimated token count (pre-computed).
        turn_added: Which loop iteration created this entry.
        version: Schema version for forward compatibility.
        metadata: Optional structured data.
    """

    zone: Zone
    source: str
    content: str
    importance: float = 0.5
    token_estimate: int = 0
    turn_added: int = 0
    version: int = 1
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Auto-estimate tokens if not provided."""
        if self.token_estimate == 0 and self.content:
            # ~4 chars per token (GPT-family heuristic)
            estimate = max(1, len(self.content) // 4)
            # frozen dataclass — use object.__setattr__
            object.__setattr__(self, "token_estimate", estimate)

    def to_dict(self) -> dict:
        """Serialize to plain dict for transport/storage."""
        return {
            "zone": self.zone.name,
            "source": self.source,
            "content": self.content,
            "importance": self.importance,
            "token_estimate": self.token_estimate,
            "turn_added": self.turn_added,
            "version": self.version,
            "metadata": self.metadata,
        }


# ── Default importance by source ──────────────────────────────────────

SOURCE_IMPORTANCE: dict[str, float] = {
    "directive": 1.0,       # Steer — never auto-prune
    "system_prompt": 0.95,  # System identity
    "user_prompt": 0.9,     # User's original ask
    "capability": 0.7,      # Discovered capabilities
    "follow_up": 0.8,       # Tool continuation
    "notification": 0.4,    # Ambient notifications
    "tool_result": 0.5,     # Tool outputs
    "history": 0.3,         # Older conversation turns
    "compressed": 0.6,      # Summarized/revised history
}


def get_importance(source: str) -> float:
    """Get default importance for a source type."""
    return SOURCE_IMPORTANCE.get(source, 0.5)
