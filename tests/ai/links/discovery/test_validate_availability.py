"""Unit tests for ValidateAvailabilityLink.

Verifies that the link correctly:
- Filters out capabilities no longer in registry
- Keeps capabilities that still exist
- Raises on missing inputs
"""

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry
from codeupipe.ai.filters.discovery.validate_availability import (
    ValidateAvailabilityLink,
)


@pytest.fixture
def registry(tmp_path):
    """Create a temp registry with a capability."""
    db = tmp_path / "test.db"
    reg = CapabilityRegistry(db)

    cap = CapabilityDefinition(
        name="add_numbers",
        description="adds two numbers",
        capability_type=CapabilityType.TOOL,
        server_name="math-server",
    )
    vec = np.zeros(1024, dtype=np.float32)
    reg.insert(cap, vec)

    return reg


@pytest.mark.asyncio
async def test_validate_keeps_existing_capabilities(registry):
    """Should keep capabilities that exist in registry."""
    ranked = [
        (CapabilityDefinition(
            name="add_numbers", description="adds two numbers",
            capability_type=CapabilityType.TOOL, server_name="math-server",
        ), 0.95),
    ]

    link = ValidateAvailabilityLink()
    ctx = Payload({
        "ranked_results": ranked,
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    available = result.get("available_results")
    assert len(available) == 1
    assert available[0][0].name == "add_numbers"


@pytest.mark.asyncio
async def test_validate_filters_missing_capabilities(registry):
    """Should filter out capabilities not in registry."""
    ranked = [
        (CapabilityDefinition(
            name="nonexistent_tool", description="does not exist",
            capability_type=CapabilityType.TOOL, server_name="ghost-server",
        ), 0.80),
    ]

    link = ValidateAvailabilityLink()
    ctx = Payload({
        "ranked_results": ranked,
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    available = result.get("available_results")
    assert len(available) == 0


@pytest.mark.asyncio
async def test_validate_mixed_results(registry):
    """Should keep existing and filter missing in same batch."""
    ranked = [
        (CapabilityDefinition(
            name="add_numbers", description="adds two numbers",
            capability_type=CapabilityType.TOOL, server_name="math-server",
        ), 0.95),
        (CapabilityDefinition(
            name="nonexistent", description="gone",
            capability_type=CapabilityType.TOOL, server_name="x",
        ), 0.80),
    ]

    link = ValidateAvailabilityLink()
    ctx = Payload({
        "ranked_results": ranked,
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    available = result.get("available_results")
    assert len(available) == 1
    assert available[0][0].name == "add_numbers"


@pytest.mark.asyncio
async def test_validate_raises_without_ranked(registry):
    """Should raise when ranked_results is missing."""
    link = ValidateAvailabilityLink()
    ctx = Payload({"capability_registry": registry})

    with pytest.raises(ValueError, match="ranked_results"):
        await link.call(ctx)


@pytest.mark.asyncio
async def test_validate_raises_without_registry():
    """Should raise when capability_registry is missing."""
    link = ValidateAvailabilityLink()
    ctx = Payload({"ranked_results": []})

    with pytest.raises(ValueError, match="capability_registry"):
        await link.call(ctx)
