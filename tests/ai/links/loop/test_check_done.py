"""RED PHASE — Tests for CheckDoneLink.

CheckDoneLink determines whether the agent loop should continue:
  - Already done? Pass through.
  - Max iterations? Mark done.
  - No follow-up/notifications? Mark done (single-turn).
  - Has follow-up or notifications? Keep going.
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.check_done import CheckDoneLink
from codeupipe.ai.loop.state import AgentState


@pytest.mark.unit
class TestCheckDoneLink:
    """Unit tests for CheckDoneLink."""

    @pytest.mark.asyncio
    async def test_already_done_passes_through(self):
        """If state is already done, passes through unchanged."""
        link = CheckDoneLink()
        state = AgentState(done=True, loop_iteration=1)
        ctx = Payload({"agent_state": state})

        result = await link.call(ctx)

        assert result.get("agent_state").done is True

    @pytest.mark.asyncio
    async def test_max_iterations_marks_done(self):
        """At max iterations, marks done."""
        link = CheckDoneLink()
        state = AgentState(loop_iteration=5, max_iterations=5)
        ctx = Payload({"agent_state": state})

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert new_state.done is True

    @pytest.mark.asyncio
    async def test_no_pending_work_marks_done(self):
        """No follow-up or notifications → single-turn, done."""
        link = CheckDoneLink()
        state = AgentState(loop_iteration=1, max_iterations=10)
        ctx = Payload({"agent_state": state})

        result = await link.call(ctx)

        assert result.get("agent_state").done is True

    @pytest.mark.asyncio
    async def test_has_follow_up_continues(self):
        """With next_prompt prepared, loop continues."""
        link = CheckDoneLink()
        state = AgentState(loop_iteration=1, max_iterations=10)
        ctx = Payload({
            "agent_state": state,
            "next_prompt": "continue",  # ReadInputLink would have set this
            "follow_up_prompt": "continue",
        })

        result = await link.call(ctx)

        assert result.get("agent_state").done is False

    @pytest.mark.asyncio
    async def test_has_notifications_continues(self):
        """With next_prompt prepared from notifications, loop continues."""
        link = CheckDoneLink()
        state = AgentState(loop_iteration=1, max_iterations=10)
        ctx = Payload({
            "agent_state": state,
            "next_prompt": "notification prompt",  # ReadInputLink would have set this
            "pending_notifications": [{"source": "ci", "message": "done"}],
        })

        result = await link.call(ctx)

        assert result.get("agent_state").done is False

    @pytest.mark.asyncio
    async def test_raises_without_agent_state(self):
        """Requires agent_state on context."""
        link = CheckDoneLink()
        ctx = Payload({})

        with pytest.raises(ValueError, match="agent_state"):
            await link.call(ctx)

    @pytest.mark.asyncio
    async def test_empty_notifications_marks_done(self):
        """Empty notification list counts as no notifications."""
        link = CheckDoneLink()
        state = AgentState(loop_iteration=1, max_iterations=10)
        ctx = Payload({
            "agent_state": state,
            "pending_notifications": [],
        })

        result = await link.call(ctx)

        assert result.get("agent_state").done is True
