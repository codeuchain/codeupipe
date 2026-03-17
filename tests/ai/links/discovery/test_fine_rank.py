"""Unit tests for FineRankLink.

Verifies that the link correctly:
- Re-ranks using full 1024-dim embeddings
- Returns top-k results per settings
- Raises on missing inputs
"""

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.config import reset_settings
from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry
from codeupipe.ai.filters.discovery.fine_rank import FineRankLink


@pytest.fixture
def registry(tmp_path):
    """Create a temp registry with capabilities."""
    db = tmp_path / "test.db"
    reg = CapabilityRegistry(db)

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
        vec = np.zeros(1024, dtype=np.float32)
        vec[i] = 1.0
        reg.insert(cap, vec)

    return reg


@pytest.fixture(autouse=True)
def _reset_settings():
    reset_settings()
    yield
    reset_settings()


@pytest.mark.asyncio
async def test_fine_rank_returns_ranked_results(registry):
    """Should return ranked_results on context."""
    query_vec = np.zeros(1024, dtype=np.float32)
    query_vec[0] = 1.0

    # Simulate coarse_results (we don't actually use them in this Link currently)
    coarse = [(CapabilityDefinition(
        name="add_numbers", description="", capability_type=CapabilityType.TOOL,
        server_name="test",
    ), 0.95)]

    link = FineRankLink()
    ctx = Payload({
        "query_embedding": query_vec,
        "coarse_results": coarse,
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    ranked = result.get("ranked_results")
    assert ranked is not None
    assert len(ranked) > 0


@pytest.mark.asyncio
async def test_fine_rank_results_sorted_by_score(registry):
    """Results should be sorted by similarity (highest first)."""
    query_vec = np.zeros(1024, dtype=np.float32)
    query_vec[0] = 1.0

    link = FineRankLink()
    ctx = Payload({
        "query_embedding": query_vec,
        "coarse_results": [],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    ranked = result.get("ranked_results")
    scores = [score for _, score in ranked]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_fine_rank_raises_without_coarse(registry):
    """Should raise when coarse_results is missing."""
    link = FineRankLink()
    ctx = Payload({
        "query_embedding": np.zeros(1024),
        "capability_registry": registry,
    })

    with pytest.raises(ValueError, match="coarse_results"):
        await link.call(ctx)


@pytest.mark.asyncio
async def test_fine_rank_raises_without_embedding(registry):
    """Should raise when query_embedding is missing."""
    link = FineRankLink()
    ctx = Payload({
        "coarse_results": [],
        "capability_registry": registry,
    })

    with pytest.raises(ValueError, match="query_embedding"):
        await link.call(ctx)


@pytest.mark.asyncio
async def test_fine_rank_raises_without_registry():
    """Should raise when capability_registry is missing."""
    link = FineRankLink()
    ctx = Payload({
        "query_embedding": np.zeros(1024),
        "coarse_results": [],
    })

    with pytest.raises(ValueError, match="capability_registry"):
        await link.call(ctx)
