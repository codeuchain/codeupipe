"""RED PHASE — Tests for ContextPruningLink.

ContextPruningLink trims stale turn history and clears consumed
response data to keep within the context token budget.
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.context_pruning import (
    ContextPruningLink,
    DEFAULT_BUDGET,
    MIN_TURNS_KEPT,
)
from codeupipe.ai.loop.state import AgentState, TurnRecord, TurnType


@pytest.mark.unit
class TestContextPruningLink:
    """Unit tests for ContextPruningLink."""

    def _make_turn(
        self,
        iteration: int = 0,
        prompt: str = "p",
        response: str | None = "r",
    ) -> TurnRecord:
        """Helper to create a TurnRecord."""
        return TurnRecord(
            iteration=iteration,
            turn_type=TurnType.USER_PROMPT,
            input_prompt=prompt,
            response_content=response,
        )

    def _state_with_turns(self, count: int, prompt_size: int = 10) -> AgentState:
        """Create a state with N turns of given prompt size."""
        state = AgentState()
        for i in range(count):
            turn = self._make_turn(
                iteration=i,
                prompt="x" * prompt_size,
                response="y" * prompt_size,
            )
            state = state.record_turn(turn)
        return state

    @pytest.mark.asyncio
    async def test_pass_through_no_pruning_needed(self):
        """With few turns and large budget, nothing is pruned."""
        link = ContextPruningLink()
        state = self._state_with_turns(2)
        ctx = Payload({"agent_state": state, "context_budget": DEFAULT_BUDGET})

        result = await link.call(ctx)

        pruned = result.get("pruned_keys") or []
        # No turn history pruning (only 2 turns, below MIN_TURNS_KEPT)
        turn_pruned = [k for k in pruned if k.startswith("turn_history")]
        assert turn_pruned == []
        assert len(result.get("agent_state").turn_history) == 2

    @pytest.mark.asyncio
    async def test_raises_without_agent_state(self):
        """Requires agent_state on context."""
        link = ContextPruningLink()
        ctx = Payload({})

        with pytest.raises(ValueError, match="agent_state"):
            await link.call(ctx)

    @pytest.mark.asyncio
    async def test_trims_history_when_over_budget(self):
        """Trims old turns when history exceeds 50% of budget."""
        link = ContextPruningLink()
        # Create 10 turns with large prompts to exceed a small budget
        state = self._state_with_turns(10, prompt_size=500)
        # Small budget — 10 turns * 1000 chars = 10000 chars = ~2500 tokens
        # 50% of 1000 token budget = 500 tokens → triggers trim
        ctx = Payload({"agent_state": state, "context_budget": 1000})

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        # Should keep at most half (5) but at least MIN_TURNS_KEPT (3)
        assert len(new_state.turn_history) == max(MIN_TURNS_KEPT, 10 // 2)
        # Kept turns should be the MOST RECENT ones
        assert new_state.turn_history[-1].iteration == 9

    @pytest.mark.asyncio
    async def test_keeps_min_turns(self):
        """Never trims below MIN_TURNS_KEPT."""
        link = ContextPruningLink()
        # 4 turns with huge prompts but tiny budget
        state = self._state_with_turns(4, prompt_size=5000)
        ctx = Payload({"agent_state": state, "context_budget": 100})

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert len(new_state.turn_history) >= MIN_TURNS_KEPT

    @pytest.mark.asyncio
    async def test_clears_last_response_event(self):
        """Prunes last_response_event after it's been processed."""
        link = ContextPruningLink()
        state = self._state_with_turns(1)  # At least 1 turn in history
        ctx = Payload({
            "agent_state": state,
            "last_response_event": {"data": {"content": "..."}},
        })

        result = await link.call(ctx)

        assert result.get("last_response_event") is None
        pruned = result.get("pruned_keys") or []
        assert "last_response_event" in pruned

    @pytest.mark.asyncio
    async def test_no_clear_when_no_history(self):
        """Doesn't clear last_response_event if no turns in history."""
        link = ContextPruningLink()
        state = AgentState()  # empty history
        ctx = Payload({
            "agent_state": state,
            "last_response_event": {"data": "something"},
        })

        result = await link.call(ctx)

        # No history → condition `len(history) > 0` is False for empty tuple
        # but the event should still be there
        # Actually let me check: history is () which has len 0
        # The condition is `ctx.get("last_response_event") is not None and len(history) > 0`
        # len(()) = 0 → False → event NOT cleared
        assert result.get("last_response_event") is not None

    @pytest.mark.asyncio
    async def test_uses_default_budget(self):
        """Uses DEFAULT_BUDGET when none on context."""
        link = ContextPruningLink()
        state = self._state_with_turns(2)
        ctx = Payload({"agent_state": state})

        result = await link.call(ctx)

        # Should pass through cleanly with default budget
        assert len(result.get("agent_state").turn_history) == 2

    @pytest.mark.asyncio
    async def test_pruned_keys_accumulate(self):
        """Pruned keys merge with existing list."""
        link = ContextPruningLink()
        state = self._state_with_turns(1)
        ctx = Payload({
            "agent_state": state,
            "last_response_event": {"data": "x"},
            "pruned_keys": ["previous_key"],
        })

        result = await link.call(ctx)

        pruned = result.get("pruned_keys")
        assert "previous_key" in pruned
        assert "last_response_event" in pruned

    @pytest.mark.asyncio
    async def test_preserves_state_fields_after_trim(self):
        """Turn-history trim preserves all other AgentState fields."""
        link = ContextPruningLink()
        state = self._state_with_turns(10, prompt_size=500)
        state = AgentState(
            loop_iteration=10,
            done=False,
            max_iterations=20,
            turn_history=state.turn_history,
            active_capabilities=("tool_a", "tool_b"),
        )
        ctx = Payload({"agent_state": state, "context_budget": 1000})

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert new_state.loop_iteration == 10
        assert new_state.done is False
        assert new_state.max_iterations == 20
        assert new_state.active_capabilities == ("tool_a", "tool_b")
