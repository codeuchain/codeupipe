"""RED PHASE — Tests for ManageStateLink.

ManageStateLink applies capability adopt/drop mutations to AgentState
based on state_updates placed on context by ProcessResponseLink
or external decision logic.
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.manage_state import ManageStateLink
from codeupipe.ai.loop.state import AgentState


@pytest.mark.unit
class TestManageStateLink:
    """Unit tests for ManageStateLink."""

    @pytest.mark.asyncio
    async def test_pass_through_no_updates(self):
        """No state_updates — state unchanged."""
        link = ManageStateLink()
        state = AgentState()
        ctx = Payload({"agent_state": state})

        result = await link.call(ctx)

        assert result.get("agent_state") is state  # same instance

    @pytest.mark.asyncio
    async def test_pass_through_empty_updates(self):
        """Empty state_updates list — state unchanged."""
        link = ManageStateLink()
        state = AgentState()
        ctx = Payload({"agent_state": state, "state_updates": []})

        result = await link.call(ctx)

        assert result.get("agent_state") is state

    @pytest.mark.asyncio
    async def test_adopt_capability(self):
        """Adopt action adds capability to state."""
        link = ManageStateLink()
        state = AgentState()
        ctx = Payload({
            "agent_state": state,
            "state_updates": [{"action": "adopt", "name": "code_review"}],
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert "code_review" in new_state.active_capabilities

    @pytest.mark.asyncio
    async def test_drop_capability(self):
        """Drop action removes capability from state."""
        link = ManageStateLink()
        state = AgentState().add_capability("old_tool")
        ctx = Payload({
            "agent_state": state,
            "state_updates": [{"action": "drop", "name": "old_tool"}],
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert "old_tool" not in new_state.active_capabilities

    @pytest.mark.asyncio
    async def test_multiple_updates(self):
        """Multiple adopt/drop in one iteration."""
        link = ManageStateLink()
        state = AgentState().add_capability("existing")
        ctx = Payload({
            "agent_state": state,
            "state_updates": [
                {"action": "adopt", "name": "new_skill"},
                {"action": "drop", "name": "existing"},
                {"action": "adopt", "name": "another_tool"},
            ],
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert "new_skill" in new_state.active_capabilities
        assert "another_tool" in new_state.active_capabilities
        assert "existing" not in new_state.active_capabilities

    @pytest.mark.asyncio
    async def test_clears_state_updates_after_consumption(self):
        """state_updates is reset to [] after processing."""
        link = ManageStateLink()
        state = AgentState()
        ctx = Payload({
            "agent_state": state,
            "state_updates": [{"action": "adopt", "name": "x"}],
        })

        result = await link.call(ctx)

        assert result.get("state_updates") == []

    @pytest.mark.asyncio
    async def test_raises_without_agent_state(self):
        """Requires agent_state on context."""
        link = ManageStateLink()
        ctx = Payload({"state_updates": [{"action": "adopt", "name": "x"}]})

        with pytest.raises(ValueError, match="agent_state"):
            await link.call(ctx)

    @pytest.mark.asyncio
    async def test_ignores_unknown_actions(self):
        """Unknown action is skipped (warning logged, not raised)."""
        link = ManageStateLink()
        state = AgentState()
        ctx = Payload({
            "agent_state": state,
            "state_updates": [{"action": "unknown", "name": "foo"}],
        })

        result = await link.call(ctx)

        # State unchanged — unknown action was a no-op
        new_state = result.get("agent_state")
        assert new_state.active_capabilities == ()
        assert result.get("state_updates") == []

    @pytest.mark.asyncio
    async def test_ignores_non_dict_updates(self):
        """Non-dict entries in state_updates are skipped."""
        link = ManageStateLink()
        state = AgentState()
        ctx = Payload({
            "agent_state": state,
            "state_updates": [
                "not-a-dict",
                {"action": "adopt", "name": "valid"},
            ],
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert "valid" in new_state.active_capabilities

    @pytest.mark.asyncio
    async def test_adopt_without_name_is_noop(self):
        """Adopt with empty name is skipped."""
        link = ManageStateLink()
        state = AgentState()
        ctx = Payload({
            "agent_state": state,
            "state_updates": [{"action": "adopt", "name": ""}],
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert new_state.active_capabilities == ()

    @pytest.mark.asyncio
    async def test_drop_missing_capability_is_noop(self):
        """Dropping a non-existent capability doesn't error."""
        link = ManageStateLink()
        state = AgentState()
        ctx = Payload({
            "agent_state": state,
            "state_updates": [{"action": "drop", "name": "nonexistent"}],
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert new_state.active_capabilities == ()

    @pytest.mark.asyncio
    async def test_preserves_other_context_keys(self):
        """ManageStateLink doesn't clobber unrelated context data."""
        link = ManageStateLink()
        state = AgentState()
        ctx = Payload({
            "agent_state": state,
            "prompt": "original prompt",
            "session": "mock_session",
            "state_updates": [{"action": "adopt", "name": "x"}],
        })

        result = await link.call(ctx)

        assert result.get("prompt") == "original prompt"
        assert result.get("session") == "mock_session"
