"""Unit tests for FetchDefinitionsLink.

Verifies that the link correctly:
- Extracts CapabilityDefinition objects from scored tuples
- Returns a flat list without scores
- Raises on missing input
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.filters.discovery.fetch_definitions import FetchDefinitionsLink


@pytest.mark.asyncio
async def test_fetch_extracts_definitions():
    """Should extract CapabilityDefinition objects from scored tuples."""
    cap_a = CapabilityDefinition(
        name="tool_a", description="A tool",
        capability_type=CapabilityType.TOOL, server_name="s1",
    )
    cap_b = CapabilityDefinition(
        name="tool_b", description="B tool",
        capability_type=CapabilityType.SKILL, server_name="s2",
    )

    link = FetchDefinitionsLink()
    ctx = Payload({"available_results": [(cap_a, 0.95), (cap_b, 0.80)]})
    result = await link.call(ctx)

    caps = result.get("capabilities")
    assert len(caps) == 2
    assert caps[0].name == "tool_a"
    assert caps[1].name == "tool_b"


@pytest.mark.asyncio
async def test_fetch_returns_list_type():
    """Should return a list of CapabilityDefinition."""
    cap = CapabilityDefinition(
        name="tool", description="A tool",
        capability_type=CapabilityType.TOOL, server_name="s",
    )

    link = FetchDefinitionsLink()
    ctx = Payload({"available_results": [(cap, 0.9)]})
    result = await link.call(ctx)

    caps = result.get("capabilities")
    assert isinstance(caps, list)
    assert all(isinstance(c, CapabilityDefinition) for c in caps)


@pytest.mark.asyncio
async def test_fetch_empty_results():
    """Should return empty list when no available results."""
    link = FetchDefinitionsLink()
    ctx = Payload({"available_results": []})
    result = await link.call(ctx)

    caps = result.get("capabilities")
    assert caps == []


@pytest.mark.asyncio
async def test_fetch_strips_scores():
    """Scores should not appear in the output list."""
    cap = CapabilityDefinition(
        name="x", description="", capability_type=CapabilityType.TOOL,
        server_name="s",
    )

    link = FetchDefinitionsLink()
    ctx = Payload({"available_results": [(cap, 0.5)]})
    result = await link.call(ctx)

    caps = result.get("capabilities")
    # Items should be CapabilityDefinition, not tuples
    assert not isinstance(caps[0], tuple)


@pytest.mark.asyncio
async def test_fetch_raises_without_available():
    """Should raise when available_results is missing."""
    link = FetchDefinitionsLink()
    ctx = Payload({})

    with pytest.raises(ValueError, match="available_results"):
        await link.call(ctx)
