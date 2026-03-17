"""ContextBudget — Track and manage token budget for the session.

Configurable token threshold determines when conversation revision
kicks in.  Tracks usage by source via ContextAttribution data
produced by ContextAttributionLink.

Usage:
    budget = ContextBudget(total_budget=128_000, revision_threshold=0.75)
    tracker = ContextBudgetTracker(budget)
    exceeded = tracker.update(attributions, total_tokens)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContextBudget:
    """Token budget configuration.

    Attributes:
        total_budget:       Max tokens the model supports.
        revision_threshold: Fraction (0.0–1.0) at which revision triggers.
                            Default 0.75 = revise at 75% usage.
        min_turns_kept:     Minimum recent turns preserved verbatim.
    """

    total_budget: int = 128_000
    revision_threshold: float = 0.75
    min_turns_kept: int = 4


@dataclass
class BudgetSnapshot:
    """Point-in-time budget status.

    Produced by ContextBudgetTracker.update() — shows whether
    revision is needed and the breakdown by source.
    """

    total_tokens: int = 0
    budget_used_pct: float = 0.0
    needs_revision: bool = False
    usage_by_source: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for audit/logging."""
        return {
            "total_tokens": self.total_tokens,
            "budget_used_pct": round(self.budget_used_pct, 2),
            "needs_revision": self.needs_revision,
            "usage_by_source": self.usage_by_source,
        }


class ContextBudgetTracker:
    """Tracks token usage against a configurable budget.

    Call update() after each turn with the latest attribution
    data.  Check the returned BudgetSnapshot to decide if
    conversation revision should run.
    """

    def __init__(self, budget: ContextBudget | None = None) -> None:
        self._budget = budget or ContextBudget()
        self._history: list[BudgetSnapshot] = []

    @property
    def budget(self) -> ContextBudget:
        return self._budget

    @property
    def last_snapshot(self) -> BudgetSnapshot | None:
        return self._history[-1] if self._history else None

    def update(
        self,
        total_tokens: int,
        usage_by_source: dict[str, int] | None = None,
    ) -> BudgetSnapshot:
        """Update budget tracking with latest token counts.

        Returns a BudgetSnapshot indicating whether revision is needed.
        """
        pct = (total_tokens / self._budget.total_budget) if self._budget.total_budget > 0 else 0.0
        needs_revision = pct >= self._budget.revision_threshold

        snapshot = BudgetSnapshot(
            total_tokens=total_tokens,
            budget_used_pct=round(pct * 100, 2),
            needs_revision=needs_revision,
            usage_by_source=usage_by_source or {},
        )

        self._history.append(snapshot)
        return snapshot

    def revision_count(self) -> int:
        """How many times has revision been triggered."""
        return sum(1 for s in self._history if s.needs_revision)
