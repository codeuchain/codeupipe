"""Billing — model multipliers and usage tracking.

Tracks premium request consumption based on GitHub Copilot's
per-request billing model. Each send_and_wait call = 1 premium
request × model multiplier.

MODEL_MULTIPLIERS maps model identifiers to their billing rate.
UsageTracker accumulates billing data across turns.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Model multipliers ────────────────────────────────────────────────
# Source: GitHub Copilot pricing (2025–2026)
# 0x = free on paid plans, extra requests $0.04 each

MODEL_MULTIPLIERS: dict[str, float] = {
    # Free tier (0x)
    "gpt-4.1": 0.0,
    "gpt-4o": 0.0,
    "gpt-5-mini": 0.0,
    "gpt-4o-mini": 0.0,
    "raptor-mini": 0.0,
    # Low tier (0.33x)
    "claude-haiku-4.5": 0.33,
    "gemini-3-flash": 0.33,
    "grok-code-fast-1": 0.33,
    # Standard tier (1x)
    "claude-sonnet-4": 1.0,
    "claude-sonnet-4.5": 1.0,
    "gpt-5": 1.0,
    "gemini-2.5-pro": 1.0,
    # Premium tier (3x)
    "claude-opus-4.5": 3.0,
    "claude-opus-4.6": 3.0,
    # Ultra tier (10x)
    "claude-opus-4": 10.0,
}


def get_multiplier(model: str) -> float:
    """Get the billing multiplier for a model.

    Unknown models default to 1.0x (safe billing assumption).
    """
    return MODEL_MULTIPLIERS.get(model, 1.0)


# ── Usage tracker ─────────────────────────────────────────────────────


@dataclass
class UsageTracker:
    """Accumulates billing data across turns.

    Attributes:
        model: The language model in use.
        total_requests: Total send_and_wait calls made.
        total_premium_requests: Cumulative premium requests (requests × multiplier).
    """

    model: str
    total_requests: int = 0
    total_premium_requests: float = 0.0

    @property
    def multiplier(self) -> float:
        """The billing multiplier for the configured model."""
        return get_multiplier(self.model)

    def record_turn(self) -> None:
        """Record one send_and_wait call."""
        self.total_requests += 1
        self.total_premium_requests += self.multiplier

    def to_dict(self) -> dict:
        """Serialize to a plain dict for events and reporting."""
        return {
            "model": self.model,
            "multiplier": self.multiplier,
            "total_requests": self.total_requests,
            "total_premium_requests": self.total_premium_requests,
        }
