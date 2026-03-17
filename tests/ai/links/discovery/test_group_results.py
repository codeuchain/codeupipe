"""Unit tests for GroupResultsLink.

Verifies that the link correctly:
- Groups capabilities by type
- Includes all CapabilityType keys (even empty)
- Handles empty input
- Handles mixed types
- Preserves capability objects unchanged
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.filters.discovery.group_results import GroupResultsLink


def _make_cap(name: str, cap_type: CapabilityType) -> CapabilityDefinition:
    """Helper to create a CapabilityDefinition."""
    return CapabilityDefinition(
        name=name,
        description=f"Description of {name}",
        capability_type=cap_type,
    )


@pytest.mark.asyncio
async def test_groups_by_type():
    """Should group capabilities into their respective type buckets."""
    caps = [
        _make_cap("add", CapabilityType.TOOL),
        _make_cap("subtract", CapabilityType.TOOL),
        _make_cap("coding", CapabilityType.SKILL),
        _make_cap("style", CapabilityType.INSTRUCTION),
    ]

    link = GroupResultsLink()
    ctx = Payload({"capabilities": caps})
    result = await link.call(ctx)

    grouped = result.get("grouped_capabilities")
    assert len(grouped["tool"]) == 2
    assert len(grouped["skill"]) == 1
    assert len(grouped["instruction"]) == 1
    assert len(grouped["plan"]) == 0
    assert len(grouped["prompt"]) == 0
    assert len(grouped["resource"]) == 0


@pytest.mark.asyncio
async def test_all_types_present_even_empty():
    """All CapabilityType keys should be present even if empty."""
    link = GroupResultsLink()
    ctx = Payload({"capabilities": []})
    result = await link.call(ctx)

    grouped = result.get("grouped_capabilities")
    for cap_type in CapabilityType:
        assert cap_type.value in grouped
        assert grouped[cap_type.value] == []


@pytest.mark.asyncio
async def test_empty_input():
    """Should return all empty buckets when no capabilities provided."""
    link = GroupResultsLink()
    ctx = Payload({"capabilities": []})
    result = await link.call(ctx)

    grouped = result.get("grouped_capabilities")
    total = sum(len(v) for v in grouped.values())
    assert total == 0


@pytest.mark.asyncio
async def test_missing_capabilities_key():
    """Should handle missing capabilities key (defaults to empty)."""
    link = GroupResultsLink()
    ctx = Payload({})
    result = await link.call(ctx)

    grouped = result.get("grouped_capabilities")
    total = sum(len(v) for v in grouped.values())
    assert total == 0


@pytest.mark.asyncio
async def test_preserves_capability_objects():
    """Grouped capabilities should be the same objects, not copies."""
    cap = _make_cap("my-tool", CapabilityType.TOOL)

    link = GroupResultsLink()
    ctx = Payload({"capabilities": [cap]})
    result = await link.call(ctx)

    grouped = result.get("grouped_capabilities")
    assert grouped["tool"][0] is cap


@pytest.mark.asyncio
async def test_all_six_types():
    """Should handle all six capability types."""
    caps = [
        _make_cap("t1", CapabilityType.TOOL),
        _make_cap("s1", CapabilityType.SKILL),
        _make_cap("p1", CapabilityType.PROMPT),
        _make_cap("r1", CapabilityType.RESOURCE),
        _make_cap("i1", CapabilityType.INSTRUCTION),
        _make_cap("pl1", CapabilityType.PLAN),
    ]

    link = GroupResultsLink()
    ctx = Payload({"capabilities": caps})
    result = await link.call(ctx)

    grouped = result.get("grouped_capabilities")
    for cap_type in CapabilityType:
        assert len(grouped[cap_type.value]) == 1


@pytest.mark.asyncio
async def test_order_preserved():
    """Capabilities within a type bucket should preserve insertion order."""
    caps = [
        _make_cap("first", CapabilityType.TOOL),
        _make_cap("second", CapabilityType.TOOL),
        _make_cap("third", CapabilityType.TOOL),
    ]

    link = GroupResultsLink()
    ctx = Payload({"capabilities": caps})
    result = await link.call(ctx)

    grouped = result.get("grouped_capabilities")
    names = [c.name for c in grouped["tool"]]
    assert names == ["first", "second", "third"]
