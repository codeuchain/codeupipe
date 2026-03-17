"""RED PHASE — Tests for ReadInputLink.

ReadInputLink prepares the next prompt for the agent:
  - First turn: uses the initial user prompt
  - Subsequent turns: uses follow-up or notifications
  - No follow-up/notifications: marks done
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.read_input import ReadInputLink
from codeupipe.ai.loop.state import AgentState


@pytest.mark.unit
class TestReadInputLink:
    """Unit tests for ReadInputLink."""

    @pytest.mark.asyncio
    async def test_first_turn_uses_initial_prompt(self):
        """On iteration 0, ReadInputLink reads the initial prompt."""
        link = ReadInputLink()
        state = AgentState()
        ctx = Payload({"prompt": "hello agent", "agent_state": state})

        result = await link.call(ctx)

        assert result.get("next_prompt") == "hello agent"
        # State should be incremented
        new_state = result.get("agent_state")
        assert new_state.loop_iteration == 1

    @pytest.mark.asyncio
    async def test_first_turn_raises_without_prompt(self):
        """First turn requires a prompt on context."""
        link = ReadInputLink()
        state = AgentState()
        ctx = Payload({"agent_state": state})

        with pytest.raises(ValueError, match="prompt"):
            await link.call(ctx)

    @pytest.mark.asyncio
    async def test_subsequent_turn_with_follow_up(self):
        """On later turns, uses follow_up_prompt if present."""
        link = ReadInputLink()
        state = AgentState(loop_iteration=1)
        ctx = Payload({
            "agent_state": state,
            "prompt": "original",
            "follow_up_prompt": "continue working",
        })

        result = await link.call(ctx)

        assert result.get("next_prompt") == "continue working"
        assert result.get("follow_up_prompt") is None  # consumed

    @pytest.mark.asyncio
    async def test_subsequent_turn_with_notifications(self):
        """On later turns, formats notifications if no follow-up."""
        link = ReadInputLink()
        state = AgentState(loop_iteration=1)
        notifications = [
            {"source": "github", "message": "PR approved"},
            {"source": "ci", "message": "Build passed"},
        ]
        ctx = Payload({
            "agent_state": state,
            "prompt": "original",
            "pending_notifications": notifications,
        })

        result = await link.call(ctx)

        next_prompt = result.get("next_prompt")
        assert "PR approved" in next_prompt
        assert "Build passed" in next_prompt
        assert result.get("pending_notifications") == []

    @pytest.mark.asyncio
    async def test_subsequent_turn_no_follow_up_marks_done(self):
        """On later turns with nothing pending, sets next_prompt=None."""
        link = ReadInputLink()
        state = AgentState(loop_iteration=1)
        ctx = Payload({
            "agent_state": state,
            "prompt": "original",
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        # ReadInputLink no longer marks done — CheckDoneLink does that
        assert new_state.done is False
        assert result.get("next_prompt") is None
        assert new_state.loop_iteration == 2

    @pytest.mark.asyncio
    async def test_raises_without_agent_state(self):
        """Requires agent_state on context."""
        link = ReadInputLink()
        ctx = Payload({"prompt": "hello"})

        with pytest.raises(ValueError, match="agent_state"):
            await link.call(ctx)

    @pytest.mark.asyncio
    async def test_notification_string_format(self):
        """Plain string notifications are formatted too."""
        link = ReadInputLink()
        state = AgentState(loop_iteration=1)
        ctx = Payload({
            "agent_state": state,
            "pending_notifications": ["test passed"],
        })

        result = await link.call(ctx)

        assert "test passed" in result.get("next_prompt")
