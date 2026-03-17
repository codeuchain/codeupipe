"""Tests for ContextAttributionLink."""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.context_attribution import ContextAttributionLink


@pytest.mark.unit
class TestContextAttributionLink:
    """Unit tests for ContextAttributionLink."""

    @pytest.mark.asyncio
    async def test_basic_attribution(self):
        """Produces attributions for all tracked sources."""
        link = ContextAttributionLink()
        ctx = Payload({
            "turn_history": ["turn1", "turn2"],
            "capabilities": [{"name": "tool_a"}],
            "grouped_capabilities": {"TOOL": [{"name": "tool_a"}]},
            "prompt": "build auth",
        })

        result = await link.call(ctx)

        attributions = result.get("context_attribution")
        assert attributions is not None
        assert len(attributions) == 6

        sources = {a.source for a in attributions}
        assert sources == {
            "turns", "capabilities", "grouped_capabilities",
            "system", "notifications", "tools",
        }

    @pytest.mark.asyncio
    async def test_total_tokens_calculated(self):
        """total_estimated_tokens is set on context."""
        link = ContextAttributionLink()
        ctx = Payload({"prompt": "hello world"})

        result = await link.call(ctx)

        total = result.get("total_estimated_tokens")
        assert isinstance(total, int)
        assert total > 0

    @pytest.mark.asyncio
    async def test_percentages_add_to_100(self):
        """Percentages should approximately sum to 100."""
        link = ContextAttributionLink()
        ctx = Payload({
            "turn_history": ["turn1", "turn2", "turn3"],
            "capabilities": [{"name": "tool_a"}, {"name": "tool_b"}],
            "grouped_capabilities": {"TOOL": [{"name": "tool_a"}]},
            "prompt": "build auth system",
            "injected_notifications": ["notification text"],
        })

        result = await link.call(ctx)

        attributions = result.get("context_attribution")
        total_pct = sum(a.percentage for a in attributions)
        assert 99.0 <= total_pct <= 101.0  # floating point tolerance

    @pytest.mark.asyncio
    async def test_empty_context(self):
        """Handles empty context gracefully."""
        link = ContextAttributionLink()
        ctx = Payload({})

        result = await link.call(ctx)

        attributions = result.get("context_attribution")
        assert attributions is not None
        total = result.get("total_estimated_tokens")
        assert isinstance(total, int)

    @pytest.mark.asyncio
    async def test_tool_attribution_from_response_event(self):
        """Tool tokens extracted from last_response_event."""
        link = ContextAttributionLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    "tool_calls": [
                        {"name": "read_file", "result": "big content here"},
                        {"name": "write_file", "result": "ok"},
                    ]
                }
            },
        })

        result = await link.call(ctx)

        attributions = result.get("context_attribution")
        tools_attr = next(a for a in attributions if a.source == "tools")
        assert tools_attr.item_count == 2
        assert tools_attr.estimated_tokens > 0

    @pytest.mark.asyncio
    async def test_item_counts(self):
        """Item counts reflect actual data counts."""
        link = ContextAttributionLink()
        ctx = Payload({
            "turn_history": ["t1", "t2", "t3"],
            "capabilities": [{"name": "a"}, {"name": "b"}],
            "grouped_capabilities": {"TOOL": [], "SKILL": []},
            "prompt": "test",
            "injected_notifications": ["n1"],
        })

        result = await link.call(ctx)

        attributions = result.get("context_attribution")
        by_source = {a.source: a for a in attributions}

        assert by_source["turns"].item_count == 3
        assert by_source["capabilities"].item_count == 2
        assert by_source["grouped_capabilities"].item_count == 2
        assert by_source["system"].item_count == 1
        assert by_source["notifications"].item_count == 1

    @pytest.mark.asyncio
    async def test_preserves_other_context(self):
        """Attribution doesn't clobber unrelated keys."""
        link = ContextAttributionLink()
        ctx = Payload({
            "prompt": "test",
            "session": "keep",
            "agent_state": "keep-too",
        })

        result = await link.call(ctx)

        assert result.get("session") == "keep"
        assert result.get("agent_state") == "keep-too"
