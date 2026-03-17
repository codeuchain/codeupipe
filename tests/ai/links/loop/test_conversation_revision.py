"""Tests for ConversationRevisionLink."""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.conversation_revision import ConversationRevisionLink
from codeupipe.ai.loop.context_budget import ContextBudget, ContextBudgetTracker
from codeupipe.ai.loop.state import AgentState, TurnRecord, TurnType


def _make_turn(iteration: int, prompt: str = "", response: str = "") -> TurnRecord:
    """Factory for test TurnRecords."""
    return TurnRecord(
        iteration=iteration,
        turn_type=TurnType.USER_PROMPT,
        input_prompt=prompt or f"prompt {iteration}",
        response_content=response or f"response {iteration}" * 50,
        tool_calls_count=1,
    )


@pytest.mark.unit
class TestConversationRevisionLink:
    """Unit tests for ConversationRevisionLink."""

    @pytest.mark.asyncio
    async def test_pass_through_no_tracker(self):
        """No tracker — pass through, revision_applied=False."""
        link = ConversationRevisionLink()
        ctx = Payload({"agent_state": AgentState()})

        result = await link.call(ctx)

        assert result.get("revision_applied") is False

    @pytest.mark.asyncio
    async def test_pass_through_no_state(self):
        """No agent_state — pass through."""
        link = ConversationRevisionLink()
        tracker = ContextBudgetTracker()
        ctx = Payload({"context_budget_tracker": tracker})

        result = await link.call(ctx)

        assert result.get("revision_applied") is False

    @pytest.mark.asyncio
    async def test_no_revision_below_threshold(self):
        """Under budget — no revision."""
        link = ConversationRevisionLink()
        budget = ContextBudget(total_budget=100_000, revision_threshold=0.75)
        tracker = ContextBudgetTracker(budget)

        turns = tuple(_make_turn(i) for i in range(8))
        state = AgentState(loop_iteration=8, turn_history=turns)

        ctx = Payload({
            "agent_state": state,
            "context_budget_tracker": tracker,
            "total_estimated_tokens": 50_000,  # 50% < 75%
        })

        result = await link.call(ctx)

        assert result.get("revision_applied") is False
        result_state = result.get("agent_state")
        assert len(result_state.turn_history) == 8  # unchanged

    @pytest.mark.asyncio
    async def test_revision_above_threshold(self):
        """Over budget — older turns get compressed."""
        link = ConversationRevisionLink()
        budget = ContextBudget(
            total_budget=100_000,
            revision_threshold=0.75,
            min_turns_kept=2,
        )
        tracker = ContextBudgetTracker(budget)

        # 6 turns, keep 2 recent, revise 4 old
        long_text = "x" * 500
        turns = tuple(
            _make_turn(i, prompt=long_text, response=long_text)
            for i in range(6)
        )
        state = AgentState(loop_iteration=6, turn_history=turns)

        ctx = Payload({
            "agent_state": state,
            "context_budget_tracker": tracker,
            "total_estimated_tokens": 80_000,  # 80% > 75%
        })

        result = await link.call(ctx)

        assert result.get("revision_applied") is True
        new_state = result.get("agent_state")
        assert len(new_state.turn_history) == 6  # same count

        # Older turns should have truncated content
        for turn in new_state.turn_history[:4]:
            assert len(turn.input_prompt) <= 130  # 120 + "..."
            assert len(turn.response_content) <= 130

        # Recent turns preserved verbatim
        assert new_state.turn_history[4].input_prompt == long_text
        assert new_state.turn_history[5].input_prompt == long_text

    @pytest.mark.asyncio
    async def test_not_enough_turns_to_revise(self):
        """Fewer turns than min_turns_kept — no revision."""
        link = ConversationRevisionLink()
        budget = ContextBudget(
            total_budget=100,
            revision_threshold=0.5,
            min_turns_kept=4,
        )
        tracker = ContextBudgetTracker(budget)

        turns = tuple(_make_turn(i) for i in range(3))
        state = AgentState(loop_iteration=3, turn_history=turns)

        ctx = Payload({
            "agent_state": state,
            "context_budget_tracker": tracker,
            "total_estimated_tokens": 90,  # 90% > 50%
        })

        result = await link.call(ctx)

        assert result.get("revision_applied") is False

    @pytest.mark.asyncio
    async def test_preserves_state_fields(self):
        """Revision preserves loop_iteration, done, max_iterations, etc."""
        link = ConversationRevisionLink()
        budget = ContextBudget(
            total_budget=100,
            revision_threshold=0.5,
            min_turns_kept=1,
        )
        tracker = ContextBudgetTracker(budget)

        turns = tuple(_make_turn(i, response="a" * 500) for i in range(5))
        state = AgentState(
            loop_iteration=5,
            done=False,
            max_iterations=20,
            turn_history=turns,
            active_capabilities=("tool_a", "tool_b"),
        )

        ctx = Payload({
            "agent_state": state,
            "context_budget_tracker": tracker,
            "total_estimated_tokens": 80,
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert new_state.loop_iteration == 5
        assert new_state.done is False
        assert new_state.max_iterations == 20
        assert new_state.active_capabilities == ("tool_a", "tool_b")

    @pytest.mark.asyncio
    async def test_attribution_data_used_for_budget(self):
        """context_attribution data is passed to budget tracker."""
        from codeupipe.ai.hooks.audit_event import ContextAttribution

        link = ConversationRevisionLink()
        budget = ContextBudget(total_budget=1000, revision_threshold=0.5)
        tracker = ContextBudgetTracker(budget)

        turns = tuple(_make_turn(i) for i in range(6))
        state = AgentState(loop_iteration=6, turn_history=turns)

        attributions = [
            ContextAttribution(source="turns", estimated_tokens=400),
            ContextAttribution(source="tools", estimated_tokens=200),
        ]

        ctx = Payload({
            "agent_state": state,
            "context_budget_tracker": tracker,
            "total_estimated_tokens": 600,
            "context_attribution": attributions,
        })

        result = await link.call(ctx)

        # Tracker should have recorded usage by source
        snap = tracker.last_snapshot
        assert snap.usage_by_source.get("turns") == 400
        assert snap.usage_by_source.get("tools") == 200
