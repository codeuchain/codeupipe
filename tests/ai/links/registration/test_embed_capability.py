"""Unit tests for EmbedCapabilityLink.

Verifies that the link correctly:
- Embeds each capability's description
- Returns (CapabilityDefinition, np.ndarray) tuples
- Raises on missing input
"""

from unittest.mock import patch

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder
from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.filters.registration.embed_capability import EmbedCapabilityLink


@pytest.fixture(autouse=True)
def _reset_embedder():
    SnowflakeArcticEmbedder.reset()
    yield
    SnowflakeArcticEmbedder.reset()


@pytest.mark.asyncio
async def test_embed_produces_tuples():
    """Should produce (CapabilityDefinition, ndarray) pairs."""
    fake_vec = np.random.randn(1024).astype(np.float32)

    with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
         patch.object(SnowflakeArcticEmbedder, "embed_document", return_value=fake_vec):

        cap = CapabilityDefinition(
            name="add", description="adds numbers",
            capability_type=CapabilityType.TOOL, server_name="s1",
        )
        link = EmbedCapabilityLink()
        ctx = Payload({"scanned_capabilities": [cap]})
        result = await link.call(ctx)

        embedded = result.get("embedded_capabilities")
        assert len(embedded) == 1
        assert isinstance(embedded[0][0], CapabilityDefinition)
        assert isinstance(embedded[0][1], np.ndarray)


@pytest.mark.asyncio
async def test_embed_uses_name_and_description():
    """Should embed 'name: description' text."""
    fake_vec = np.random.randn(1024).astype(np.float32)

    with patch.object(
        SnowflakeArcticEmbedder, "__init__", return_value=None,
    ), patch.object(
        SnowflakeArcticEmbedder, "embed_document",
        return_value=fake_vec,
    ) as mock_embed:

        cap = CapabilityDefinition(
            name="weather", description="fetches weather data",
            capability_type=CapabilityType.TOOL, server_name="s1",
        )
        link = EmbedCapabilityLink()
        ctx = Payload({"scanned_capabilities": [cap]})
        await link.call(ctx)

        mock_embed.assert_called_once_with("weather: fetches weather data")


@pytest.mark.asyncio
async def test_embed_name_only_when_no_description():
    """Should embed just name when description is empty."""
    fake_vec = np.random.randn(1024).astype(np.float32)

    with patch.object(
        SnowflakeArcticEmbedder, "__init__", return_value=None,
    ), patch.object(
        SnowflakeArcticEmbedder, "embed_document",
        return_value=fake_vec,
    ) as mock_embed:

        cap = CapabilityDefinition(
            name="my_tool", description="",
            capability_type=CapabilityType.TOOL, server_name="s1",
        )
        link = EmbedCapabilityLink()
        ctx = Payload({"scanned_capabilities": [cap]})
        await link.call(ctx)

        mock_embed.assert_called_once_with("my_tool")


@pytest.mark.asyncio
async def test_embed_multiple_capabilities():
    """Should embed all capabilities in the list."""
    fake_vec = np.random.randn(1024).astype(np.float32)

    with patch.object(
        SnowflakeArcticEmbedder, "__init__", return_value=None,
    ), patch.object(
        SnowflakeArcticEmbedder, "embed_document",
        return_value=fake_vec,
    ) as mock_embed:

        caps = [
            CapabilityDefinition(
                name=f"t{i}", description=f"desc{i}",
                capability_type=CapabilityType.TOOL, server_name="s1",
            )
            for i in range(3)
        ]
        link = EmbedCapabilityLink()
        ctx = Payload({"scanned_capabilities": caps})
        result = await link.call(ctx)

        embedded = result.get("embedded_capabilities")
        assert len(embedded) == 3
        assert mock_embed.call_count == 3


@pytest.mark.asyncio
async def test_embed_raises_without_capabilities():
    """Should raise when scanned_capabilities is missing."""
    link = EmbedCapabilityLink()
    ctx = Payload({})

    with pytest.raises(ValueError, match="scanned_capabilities"):
        await link.call(ctx)
