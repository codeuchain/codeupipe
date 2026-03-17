"""Unit tests for EmbedQueryLink.

Verifies that the link correctly:
- Embeds intent text into a query vector
- Raises on missing intent
- Places query_embedding on context
"""

from unittest.mock import patch

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder
from codeupipe.ai.filters.discovery.embed_query import EmbedQueryLink


@pytest.fixture(autouse=True)
def _reset_embedder():
    """Reset embedder singleton between tests."""
    SnowflakeArcticEmbedder.reset()
    yield
    SnowflakeArcticEmbedder.reset()


@pytest.mark.asyncio
async def test_embed_query_produces_embedding():
    """Should place a numpy array on context as query_embedding."""
    fake_vec = np.random.randn(1024).astype(np.float32)

    with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
         patch.object(SnowflakeArcticEmbedder, "embed_query", return_value=fake_vec):

        link = EmbedQueryLink()
        ctx = Payload({"intent": "calculate the sum of two numbers"})
        result = await link.call(ctx)

        assert result.get("query_embedding") is not None
        assert isinstance(result.get("query_embedding"), np.ndarray)
        assert result.get("query_embedding").shape == (1024,)


@pytest.mark.asyncio
async def test_embed_query_calls_embedder_with_intent():
    """Should pass the intent string to embed_query."""
    fake_vec = np.random.randn(1024).astype(np.float32)

    with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
         patch.object(SnowflakeArcticEmbedder, "embed_query", return_value=fake_vec) as mock_embed:

        link = EmbedQueryLink()
        ctx = Payload({"intent": "find weather data"})
        await link.call(ctx)

        mock_embed.assert_called_once_with("find weather data")


@pytest.mark.asyncio
async def test_embed_query_raises_without_intent():
    """Should raise ValueError when intent is missing."""
    link = EmbedQueryLink()
    ctx = Payload({})

    with pytest.raises(ValueError, match="intent"):
        await link.call(ctx)


@pytest.mark.asyncio
async def test_embed_query_raises_on_empty_intent():
    """Should raise ValueError when intent is empty string."""
    link = EmbedQueryLink()
    ctx = Payload({"intent": ""})

    with pytest.raises(ValueError, match="intent"):
        await link.call(ctx)


@pytest.mark.asyncio
async def test_embed_query_preserves_context():
    """Should preserve existing context values."""
    fake_vec = np.random.randn(1024).astype(np.float32)

    with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
         patch.object(SnowflakeArcticEmbedder, "embed_query", return_value=fake_vec):

        link = EmbedQueryLink()
        ctx = Payload({"intent": "test", "other_key": "preserved"})
        result = await link.call(ctx)

        assert result.get("other_key") == "preserved"
        assert result.get("intent") == "test"
