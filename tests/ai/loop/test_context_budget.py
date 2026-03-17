"""Tests for ContextBudget and ContextBudgetTracker."""

import pytest

from codeupipe.ai.loop.context_budget import (
    BudgetSnapshot,
    ContextBudget,
    ContextBudgetTracker,
)


@pytest.mark.unit
class TestContextBudget:
    """Unit tests for ContextBudget dataclass."""

    def test_defaults(self):
        budget = ContextBudget()
        assert budget.total_budget == 128_000
        assert budget.revision_threshold == 0.75
        assert budget.min_turns_kept == 4

    def test_custom_values(self):
        budget = ContextBudget(
            total_budget=64_000,
            revision_threshold=0.5,
            min_turns_kept=2,
        )
        assert budget.total_budget == 64_000
        assert budget.revision_threshold == 0.5
        assert budget.min_turns_kept == 2


@pytest.mark.unit
class TestBudgetSnapshot:
    """Unit tests for BudgetSnapshot."""

    def test_defaults(self):
        snap = BudgetSnapshot()
        assert snap.total_tokens == 0
        assert snap.budget_used_pct == 0.0
        assert snap.needs_revision is False
        assert snap.usage_by_source == {}

    def test_to_dict(self):
        snap = BudgetSnapshot(
            total_tokens=5000,
            budget_used_pct=50.0,
            needs_revision=False,
            usage_by_source={"turns": 3000, "tools": 2000},
        )
        d = snap.to_dict()
        assert d["total_tokens"] == 5000
        assert d["budget_used_pct"] == 50.0
        assert d["needs_revision"] is False
        assert d["usage_by_source"] == {"turns": 3000, "tools": 2000}


@pytest.mark.unit
class TestContextBudgetTracker:
    """Unit tests for ContextBudgetTracker."""

    def test_no_revision_below_threshold(self):
        budget = ContextBudget(total_budget=100, revision_threshold=0.75)
        tracker = ContextBudgetTracker(budget)

        snap = tracker.update(50)  # 50% usage

        assert snap.needs_revision is False
        assert snap.budget_used_pct == 50.0

    def test_revision_at_threshold(self):
        budget = ContextBudget(total_budget=100, revision_threshold=0.75)
        tracker = ContextBudgetTracker(budget)

        snap = tracker.update(75)  # exactly 75%

        assert snap.needs_revision is True
        assert snap.budget_used_pct == 75.0

    def test_revision_above_threshold(self):
        budget = ContextBudget(total_budget=100, revision_threshold=0.75)
        tracker = ContextBudgetTracker(budget)

        snap = tracker.update(90)  # 90%

        assert snap.needs_revision is True

    def test_usage_by_source_recorded(self):
        tracker = ContextBudgetTracker()
        usage = {"turns": 3000, "tools": 1000, "system": 500}

        snap = tracker.update(4500, usage)

        assert snap.usage_by_source == usage

    def test_last_snapshot(self):
        tracker = ContextBudgetTracker()

        assert tracker.last_snapshot is None

        tracker.update(1000)
        assert tracker.last_snapshot is not None
        assert tracker.last_snapshot.total_tokens == 1000

    def test_revision_count(self):
        budget = ContextBudget(total_budget=100, revision_threshold=0.5)
        tracker = ContextBudgetTracker(budget)

        tracker.update(30)  # below
        tracker.update(60)  # above
        tracker.update(40)  # below
        tracker.update(80)  # above

        assert tracker.revision_count() == 2

    def test_zero_budget_no_crash(self):
        budget = ContextBudget(total_budget=0)
        tracker = ContextBudgetTracker(budget)

        snap = tracker.update(100)

        assert snap.budget_used_pct == 0.0
