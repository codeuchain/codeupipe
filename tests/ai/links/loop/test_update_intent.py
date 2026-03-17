"""RED PHASE — Tests for UpdateIntentLink.

UpdateIntentLink detects intent shifts from agent output and
updates the intent key on context for RediscoverLink.
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.update_intent import UpdateIntentLink


@pytest.mark.unit
class TestUpdateIntentLink:
    """Unit tests for UpdateIntentLink."""

    @pytest.mark.asyncio
    async def test_pass_through_no_changes(self):
        """No state_updates and no follow_up_intent — pass through."""
        link = UpdateIntentLink()
        ctx = Payload({"intent": "build auth", "prompt": "build auth"})

        result = await link.call(ctx)

        assert result.get("intent") == "build auth"
        assert result.get("intent_changed") is False

    @pytest.mark.asyncio
    async def test_explicit_intent_update_via_state_updates(self):
        """Agent sends update_intent action in state_updates."""
        link = UpdateIntentLink()
        ctx = Payload({
            "intent": "build auth",
            "state_updates": [
                {"action": "update_intent", "intent": "write tests for auth"},
            ],
        })

        result = await link.call(ctx)

        assert result.get("intent") == "write tests for auth"
        assert result.get("intent_changed") is True
        assert result.get("last_intent") == "build auth"

    @pytest.mark.asyncio
    async def test_consumes_update_intent_from_state_updates(self):
        """update_intent is consumed — not passed to ManageStateLink."""
        link = UpdateIntentLink()
        ctx = Payload({
            "intent": "old",
            "state_updates": [
                {"action": "update_intent", "intent": "new"},
                {"action": "adopt", "name": "tool_a"},
            ],
        })

        result = await link.call(ctx)

        # update_intent consumed, adopt remains
        remaining = result.get("state_updates")
        assert len(remaining) == 1
        assert remaining[0]["action"] == "adopt"

    @pytest.mark.asyncio
    async def test_follow_up_intent_key(self):
        """External follow_up_intent key triggers intent shift."""
        link = UpdateIntentLink()
        ctx = Payload({
            "intent": "original",
            "follow_up_intent": "debug the failing test",
        })

        result = await link.call(ctx)

        assert result.get("intent") == "debug the failing test"
        assert result.get("intent_changed") is True
        assert result.get("follow_up_intent") is None  # consumed

    @pytest.mark.asyncio
    async def test_same_intent_no_change(self):
        """Intent same as current — not flagged as changed."""
        link = UpdateIntentLink()
        ctx = Payload({
            "intent": "build auth",
            "state_updates": [
                {"action": "update_intent", "intent": "build auth"},
            ],
        })

        result = await link.call(ctx)

        assert result.get("intent_changed") is False

    @pytest.mark.asyncio
    async def test_empty_intent_ignored(self):
        """Empty intent string is ignored."""
        link = UpdateIntentLink()
        ctx = Payload({
            "intent": "build auth",
            "state_updates": [
                {"action": "update_intent", "intent": "   "},
            ],
        })

        result = await link.call(ctx)

        assert result.get("intent_changed") is False

    @pytest.mark.asyncio
    async def test_falls_back_to_prompt_as_intent(self):
        """If no intent key, uses prompt as current intent."""
        link = UpdateIntentLink()
        ctx = Payload({
            "prompt": "build something",
            "follow_up_intent": "test it",
        })

        result = await link.call(ctx)

        assert result.get("intent") == "test it"
        assert result.get("intent_changed") is True
        assert result.get("last_intent") == "build something"

    @pytest.mark.asyncio
    async def test_follow_up_intent_takes_precedence(self):
        """follow_up_intent overrides state_update intent."""
        link = UpdateIntentLink()
        ctx = Payload({
            "intent": "old",
            "state_updates": [
                {"action": "update_intent", "intent": "from_state"},
            ],
            "follow_up_intent": "from_external",
        })

        result = await link.call(ctx)

        # follow_up_intent is checked after state_updates,
        # so it overwrites
        assert result.get("intent") == "from_external"

    @pytest.mark.asyncio
    async def test_non_dict_state_updates_preserved(self):
        """Non-dict entries in state_updates pass through."""
        link = UpdateIntentLink()
        ctx = Payload({
            "intent": "old",
            "state_updates": [
                "not a dict",
                {"action": "update_intent", "intent": "new"},
            ],
        })

        result = await link.call(ctx)

        remaining = result.get("state_updates")
        assert len(remaining) == 1
        assert remaining[0] == "not a dict"
