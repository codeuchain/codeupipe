"""Integration tests for IntentDiscoveryChain.

Tests the full discovery pipeline:
  EmbedQuery → CoarseSearch → FineRank → ValidateAvailability → FetchDefinitions
"""

from unittest.mock import patch

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.pipelines.intent_discovery import build_intent_discovery_chain
from codeupipe.ai.config import reset_settings
from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder
from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry


@pytest.fixture(autouse=True)
def _clean():
    SnowflakeArcticEmbedder.reset()
    reset_settings()
    yield
    SnowflakeArcticEmbedder.reset()
    reset_settings()


@pytest.fixture
def registry_with_tools(tmp_path):
    """Registry pre-loaded with 3 tool embeddings."""
    db = tmp_path / "test.db"
    reg = CapabilityRegistry(db)

    tools = [
        ("add_numbers", "adds two numbers together to calculate a sum"),
        ("get_weather", "fetches current weather forecast data for a city"),
        ("send_email", "sends an email message to a recipient"),
    ]

    for i, (name, desc) in enumerate(tools):
        cap = CapabilityDefinition(
            name=name,
            description=desc,
            capability_type=CapabilityType.TOOL,
            server_name="test-server",
        )
        # Create distinct embeddings — weighted by index
        vec = np.zeros(1024, dtype=np.float32)
        vec[i * 10:(i + 1) * 10] = 1.0
        vec = vec / np.linalg.norm(vec)  # normalise
        reg.insert(cap, vec)

    return reg


def _fake_embed(text: str) -> np.ndarray:
    """Produce a fake embedding that's closest to 'add_numbers' pattern."""
    vec = np.zeros(1024, dtype=np.float32)
    vec[0:10] = 1.0  # Matches add_numbers pattern
    return vec / np.linalg.norm(vec)


@pytest.mark.integration
class TestIntentDiscoveryChain:
    """Integration tests for the intent discovery pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_returns_capabilities(self, registry_with_tools):
        """Should return matching CapabilityDefinition objects."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_query", side_effect=_fake_embed):

            chain = build_intent_discovery_chain()
            ctx = Payload({
                "intent": "calculate the sum of two numbers",
                "capability_registry": registry_with_tools,
            })
            result = await chain.run(ctx)

            capabilities = result.get("capabilities")
            assert capabilities is not None
            assert len(capabilities) > 0
            assert all(isinstance(c, CapabilityDefinition) for c in capabilities)

    @pytest.mark.asyncio
    async def test_pipeline_finds_matching_tool(self, registry_with_tools):
        """Should rank the matching tool highest."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_query", side_effect=_fake_embed):

            chain = build_intent_discovery_chain()
            ctx = Payload({
                "intent": "add numbers",
                "capability_registry": registry_with_tools,
            })
            result = await chain.run(ctx)

            capabilities = result.get("capabilities")
            # add_numbers should be among results (best match)
            names = [c.name for c in capabilities]
            assert "add_numbers" in names

    @pytest.mark.asyncio
    async def test_pipeline_populates_intermediate_context(self, registry_with_tools):
        """Should have all intermediate context keys set."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_query", side_effect=_fake_embed):

            chain = build_intent_discovery_chain()
            ctx = Payload({
                "intent": "math",
                "capability_registry": registry_with_tools,
            })
            result = await chain.run(ctx)

            assert result.get("query_embedding") is not None
            assert result.get("coarse_results") is not None
            assert result.get("ranked_results") is not None
            assert result.get("available_results") is not None
            assert result.get("capabilities") is not None

    @pytest.mark.asyncio
    async def test_pipeline_empty_registry(self, tmp_path):
        """Should return empty capabilities from an empty registry."""
        db = tmp_path / "empty.db"
        reg = CapabilityRegistry(db)

        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_query", side_effect=_fake_embed):

            chain = build_intent_discovery_chain()
            ctx = Payload({
                "intent": "anything",
                "capability_registry": reg,
            })
            result = await chain.run(ctx)

            capabilities = result.get("capabilities")
            assert capabilities == []
