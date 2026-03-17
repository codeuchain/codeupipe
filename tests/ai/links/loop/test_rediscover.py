"""RED PHASE — Tests for RediscoverLink.

RediscoverLink re-runs the discovery pipeline when UpdateIntentLink
sets intent_changed=True, refreshing capabilities for the new intent.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from codeupipe import Payload

from codeupipe.ai.discovery.registry import CapabilityRegistry
from codeupipe.ai.filters.loop.rediscover import RediscoverLink


def _mock_registry() -> MagicMock:
    """Create a MagicMock that passes isinstance(x, CapabilityRegistry)."""
    return MagicMock(spec=CapabilityRegistry)


@pytest.mark.unit
class TestRediscoverLink:
    """Unit tests for RediscoverLink."""

    @pytest.mark.asyncio
    async def test_pass_through_no_change(self):
        """intent_changed=False — pass through unchanged."""
        link = RediscoverLink()
        ctx = Payload({
            "intent": "build auth",
            "intent_changed": False,
            "capabilities": ["existing"],
        })

        result = await link.call(ctx)

        assert result.get("capabilities") == ["existing"]

    @pytest.mark.asyncio
    async def test_pass_through_missing_flag(self):
        """No intent_changed key — pass through."""
        link = RediscoverLink()
        ctx = Payload({"intent": "build auth"})

        result = await link.call(ctx)

        assert result.get("intent") == "build auth"

    @pytest.mark.asyncio
    async def test_pass_through_no_registry(self):
        """intent_changed=True but no registry — pass through."""
        link = RediscoverLink()
        ctx = Payload({
            "intent": "new intent",
            "intent_changed": True,
        })

        result = await link.call(ctx)

        # No crash, graceful pass-through
        assert result.get("intent") == "new intent"

    @pytest.mark.asyncio
    async def test_pass_through_wrong_registry_type(self):
        """intent_changed=True but registry is wrong type — pass through."""
        link = RediscoverLink()
        ctx = Payload({
            "intent": "new intent",
            "intent_changed": True,
            "capability_registry": "not-a-registry",
        })

        result = await link.call(ctx)

        assert result.get("intent") == "new intent"

    @pytest.mark.asyncio
    async def test_pass_through_empty_intent(self):
        """intent_changed=True but empty intent — pass through."""
        link = RediscoverLink()
        registry = _mock_registry()

        ctx = Payload({
            "intent": "",
            "intent_changed": True,
            "capability_registry": registry,
        })

        result = await link.call(ctx)

        assert result.get("capabilities") is None

    @pytest.mark.asyncio
    async def test_runs_discovery_chain_on_intent_change(self):
        """intent_changed=True + valid registry → runs discovery chain."""
        link = RediscoverLink()
        registry = _mock_registry()
        mock_chain = AsyncMock()

        fresh_caps = [{"name": "tool_a"}, {"name": "tool_b"}]
        fresh_grouped = {"TOOL": [{"name": "tool_a"}], "SKILL": [{"name": "tool_b"}]}

        # Mock the discovery chain to return refreshed capabilities
        async def fake_run(ctx):
            return ctx.insert("capabilities", fresh_caps).insert(
                "grouped_capabilities", fresh_grouped
            )

        mock_chain.run = fake_run

        with patch(
            "codeupipe.ai.pipelines.intent_discovery.build_intent_discovery_chain",
            return_value=mock_chain,
        ):
            ctx = Payload({
                "intent": "write tests for auth",
                "intent_changed": True,
                "capability_registry": registry,
                "capabilities": [{"name": "old_tool"}],
            })

            result = await link.call(ctx)

            assert result.get("capabilities") == fresh_caps
            assert result.get("grouped_capabilities") == fresh_grouped

    @pytest.mark.asyncio
    async def test_preserves_other_context_keys(self):
        """Rediscovery doesn't clobber unrelated context."""
        link = RediscoverLink()
        registry = _mock_registry()
        mock_chain = AsyncMock()

        async def fake_run(ctx):
            return ctx.insert("capabilities", []).insert(
                "grouped_capabilities", {}
            )

        mock_chain.run = fake_run

        with patch(
            "codeupipe.ai.pipelines.intent_discovery.build_intent_discovery_chain",
            return_value=mock_chain,
        ):
            ctx = Payload({
                "intent": "new intent",
                "intent_changed": True,
                "capability_registry": registry,
                "session": "keep-this",
                "agent_state": "keep-this-too",
            })

            result = await link.call(ctx)

            assert result.get("session") == "keep-this"
            assert result.get("agent_state") == "keep-this-too"

    @pytest.mark.asyncio
    async def test_empty_discovery_result(self):
        """Discovery returns empty — context updated to empty."""
        link = RediscoverLink()
        registry = _mock_registry()
        mock_chain = AsyncMock()

        async def fake_run(ctx):
            # Discovery found nothing — returns empty results
            return ctx.insert("capabilities", []).insert(
                "grouped_capabilities", {}
            )

        mock_chain.run = fake_run

        with patch(
            "codeupipe.ai.pipelines.intent_discovery.build_intent_discovery_chain",
            return_value=mock_chain,
        ):
            ctx = Payload({
                "intent": "obscure intent",
                "intent_changed": True,
                "capability_registry": registry,
                "capabilities": [{"name": "old"}],
            })

            result = await link.call(ctx)

            assert result.get("capabilities") == []
            assert result.get("grouped_capabilities") == {}
