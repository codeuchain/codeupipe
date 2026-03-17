"""RED PHASE — Tests for ProcessResponseLink.

ProcessResponseLink records the turn in AgentState from the model response.
LanguageModelLink places ``response`` (str) on context before this runs.
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.process_response import ProcessResponseLink
from codeupipe.ai.loop.state import AgentState, TurnType


@pytest.mark.unit
class TestProcessResponseLink:
    """Unit tests for ProcessResponseLink."""

    @pytest.mark.asyncio
    async def test_records_response_content(self):
        """Records response string set by LanguageModelLink."""
        link = ProcessResponseLink()

        state = AgentState(loop_iteration=1)
        ctx = Payload({
            "agent_state": state,
            "response": "Here's your answer",
            "next_prompt": "hello",
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert len(new_state.turn_history) == 1
        assert new_state.turn_history[0].response_content == "Here's your answer"

    @pytest.mark.asyncio
    async def test_records_turn_in_history(self):
        """Appends a TurnRecord to agent_state history."""
        link = ProcessResponseLink()

        state = AgentState(loop_iteration=1)
        ctx = Payload({
            "agent_state": state,
            "response": "Done",
            "next_prompt": "do something",
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert len(new_state.turn_history) == 1

        turn = new_state.turn_history[0]
        assert turn.iteration == 0  # iteration - 1 (already incremented by ReadInput)
        assert turn.input_prompt == "do something"
        assert turn.response_content == "Done"

    @pytest.mark.asyncio
    async def test_handles_none_response(self):
        """Handles None response (timeout or error)."""
        link = ProcessResponseLink()

        state = AgentState(loop_iteration=1)
        ctx = Payload({
            "agent_state": state,
            "response": None,
            "next_prompt": "hello",
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert len(new_state.turn_history) == 1
        assert new_state.turn_history[0].response_content is None

    @pytest.mark.asyncio
    async def test_first_turn_type_is_user_prompt(self):
        """First iteration (loop_iteration=1) → USER_PROMPT type."""
        link = ProcessResponseLink()

        state = AgentState(loop_iteration=1)
        ctx = Payload({
            "agent_state": state,
            "response": "Hi",
            "next_prompt": "hello",
        })

        result = await link.call(ctx)

        turn = result.get("agent_state").turn_history[0]
        assert turn.turn_type == TurnType.USER_PROMPT

    @pytest.mark.asyncio
    async def test_subsequent_turn_type_is_follow_up(self):
        """Later iterations → FOLLOW_UP type."""
        link = ProcessResponseLink()

        state = AgentState(loop_iteration=3)
        ctx = Payload({
            "agent_state": state,
            "response": "Continuing",
            "next_prompt": "next step",
        })

        result = await link.call(ctx)

        turn = result.get("agent_state").turn_history[0]
        assert turn.turn_type == TurnType.FOLLOW_UP

    @pytest.mark.asyncio
    async def test_raises_without_agent_state(self):
        """Requires agent_state on context."""
        link = ProcessResponseLink()
        ctx = Payload({"response": "hi", "next_prompt": "hi"})

        with pytest.raises(ValueError, match="agent_state"):
            await link.call(ctx)

    @pytest.mark.asyncio
    async def test_skips_when_no_prompt(self):
        """Skips processing when next_prompt is None (nothing was sent)."""
        link = ProcessResponseLink()

        state = AgentState(loop_iteration=1)
        ctx = Payload({
            "agent_state": state,
            "response": "leftover from previous iteration",
            "next_prompt": None,
        })

        result = await link.call(ctx)

        # Should skip — no turn recorded
        new_state = result.get("agent_state")
        assert len(new_state.turn_history) == 0
