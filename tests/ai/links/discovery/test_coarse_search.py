"""Unit tests for CoarseSearchLink.

Verifies that the link correctly:
- Performs vector search with coarse dims
- Passes settings for top_k and coarse_dims
- Raises on missing inputs
"""

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.config import reset_settings
from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry
from codeupipe.ai.filters.discovery.coarse_search import CoarseSearchLink


@pytest.fixture
def registry(tmp_path):
    """Create a temp registry with some capabilities."""
    db = tmp_path / "test.db"
    reg = CapabilityRegistry(db)

    # Insert 3 capabilities with embeddings
    for i, (name, desc) in enumerate([
        ("add_numbers", "adds two numbers together"),
        ("get_weather", "fetches current weather data"),
        ("send_email", "sends an email message"),
    ]):
        cap = CapabilityDefinition(
            name=name,
            description=desc,
            capability_type=CapabilityType.TOOL,
            server_name="test-server",
        )
        # Create a recognisable embedding for each
        vec = np.zeros(1024, dtype=np.float32)
        vec[i] = 1.0  # One-hot at position i
        reg.insert(cap, vec)

    return reg


@pytest.fixture(autouse=True)
def _reset_settings():
    reset_settings()
    yield
    reset_settings()


@pytest.mark.asyncio
async def test_coarse_search_returns_results(registry):
    """Should return coarse_results on context."""
    query_vec = np.zeros(1024, dtype=np.float32)
    query_vec[0] = 1.0  # Most similar to add_numbers

    link = CoarseSearchLink()
    ctx = Payload({
        "query_embedding": query_vec,
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    coarse = result.get("coarse_results")
    assert coarse is not None
    assert len(coarse) > 0


@pytest.mark.asyncio
async def test_coarse_search_results_are_scored_tuples(registry):
    """Results should be (CapabilityDefinition, float) tuples."""
    query_vec = np.random.randn(1024).astype(np.float32)

    link = CoarseSearchLink()
    ctx = Payload({
        "query_embedding": query_vec,
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    coarse = result.get("coarse_results")
    for cap, score in coarse:
        assert isinstance(cap, CapabilityDefinition)
        assert isinstance(score, float)


@pytest.mark.asyncio
async def test_coarse_search_raises_without_embedding(registry):
    """Should raise when query_embedding is missing."""
    link = CoarseSearchLink()
    ctx = Payload({"capability_registry": registry})

    with pytest.raises(ValueError, match="query_embedding"):
        await link.call(ctx)


@pytest.mark.asyncio
async def test_coarse_search_raises_without_registry():
    """Should raise when capability_registry is missing."""
    link = CoarseSearchLink()
    ctx = Payload({"query_embedding": np.zeros(1024)})

    with pytest.raises(ValueError, match="capability_registry"):
        await link.call(ctx)


@pytest.mark.asyncio
async def test_coarse_search_with_type_filter(registry):
    """Should pass capability_type filter to vector_search."""
    query_vec = np.random.randn(1024).astype(np.float32)

    link = CoarseSearchLink()
    ctx = Payload({
        "query_embedding": query_vec,
        "capability_registry": registry,
        "capability_type": CapabilityType.TOOL,
    })
    result = await link.call(ctx)

    coarse = result.get("coarse_results")
    assert coarse is not None
