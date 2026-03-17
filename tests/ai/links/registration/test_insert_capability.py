"""Unit tests for InsertCapabilityLink.

Verifies that the link correctly:
- Inserts capabilities into registry
- Skips duplicates
- Returns registered_count
- Raises on missing inputs
"""

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry
from codeupipe.ai.filters.registration.insert_capability import InsertCapabilityLink


@pytest.fixture
def registry(tmp_path):
    """Create a fresh temp registry."""
    db = tmp_path / "test.db"
    return CapabilityRegistry(db)


@pytest.mark.asyncio
async def test_insert_stores_capabilities(registry):
    """Should insert capabilities into the registry."""
    cap = CapabilityDefinition(
        name="add", description="adds numbers",
        capability_type=CapabilityType.TOOL, server_name="s1",
    )
    vec = np.random.randn(1024).astype(np.float32)

    link = InsertCapabilityLink()
    ctx = Payload({
        "embedded_capabilities": [(cap, vec)],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    assert result.get("registered_count") == 1
    assert registry.get_by_name("add") is not None


@pytest.mark.asyncio
async def test_insert_skips_duplicates(registry):
    """Should not insert a capability that already exists."""
    cap = CapabilityDefinition(
        name="add", description="adds numbers",
        capability_type=CapabilityType.TOOL, server_name="s1",
    )
    vec = np.random.randn(1024).astype(np.float32)

    # Pre-insert
    registry.insert(cap, vec)

    # Try to insert again via Link
    cap2 = CapabilityDefinition(
        name="add", description="adds numbers (duplicate)",
        capability_type=CapabilityType.TOOL, server_name="s1",
    )
    link = InsertCapabilityLink()
    ctx = Payload({
        "embedded_capabilities": [(cap2, vec)],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    assert result.get("registered_count") == 0


@pytest.mark.asyncio
async def test_insert_multiple(registry):
    """Should insert multiple capabilities, counting correctly."""
    caps = []
    for i in range(3):
        cap = CapabilityDefinition(
            name=f"tool_{i}", description=f"desc {i}",
            capability_type=CapabilityType.TOOL, server_name="s1",
        )
        vec = np.random.randn(1024).astype(np.float32)
        caps.append((cap, vec))

    link = InsertCapabilityLink()
    ctx = Payload({
        "embedded_capabilities": caps,
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    assert result.get("registered_count") == 3
    assert len(registry.list_all()) == 3


@pytest.mark.asyncio
async def test_insert_raises_without_embedded():
    """Should raise when embedded_capabilities is missing."""
    link = InsertCapabilityLink()
    ctx = Payload({"capability_registry": "not_used"})

    with pytest.raises(ValueError, match="embedded_capabilities"):
        await link.call(ctx)


@pytest.mark.asyncio
async def test_insert_raises_without_registry():
    """Should raise when capability_registry is missing."""
    link = InsertCapabilityLink()
    ctx = Payload({"embedded_capabilities": []})

    with pytest.raises(ValueError, match="capability_registry"):
        await link.call(ctx)
