"""Integration tests for CapabilityRegistrationChain.

Tests the full registration pipeline:
  ScanServer → EmbedCapability → InsertCapability
"""

from unittest.mock import patch

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.pipelines.capability_registration import (
    build_capability_registration_chain,
)
from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder
from codeupipe.ai.discovery.registry import CapabilityRegistry


@pytest.fixture(autouse=True)
def _clean():
    SnowflakeArcticEmbedder.reset()
    yield
    SnowflakeArcticEmbedder.reset()


@pytest.fixture
def empty_registry(tmp_path):
    """Create a fresh empty registry."""
    db = tmp_path / "test.db"
    return CapabilityRegistry(db)


def _fake_embed_doc(text: str) -> np.ndarray:
    """Fake embedding for documents."""
    vec = np.random.randn(1024).astype(np.float32)
    return vec / np.linalg.norm(vec)


@pytest.mark.integration
class TestCapabilityRegistrationChain:
    """Integration tests for the capability registration pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_registers_tools(self, empty_registry):
        """Should register all scanned tools in the registry."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_fake_embed_doc):

            chain = build_capability_registration_chain()
            ctx = Payload({
                "server_name": "math-server",
                "server_tools": [
                    {"name": "add", "description": "adds numbers"},
                    {"name": "subtract", "description": "subtracts numbers"},
                ],
                "capability_registry": empty_registry,
            })
            result = await chain.run(ctx)

            assert result.get("registered_count") == 2
            assert len(empty_registry.list_all()) == 2

    @pytest.mark.asyncio
    async def test_pipeline_stores_embeddings(self, empty_registry):
        """Registered capabilities should have embeddings."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_fake_embed_doc):

            chain = build_capability_registration_chain()
            ctx = Payload({
                "server_name": "s1",
                "server_tools": [
                    {"name": "tool_a", "description": "does A"},
                ],
                "capability_registry": empty_registry,
            })
            await chain.run(ctx)

            cap = empty_registry.get_by_name("tool_a")
            assert cap is not None
            assert cap.embedding is not None

    @pytest.mark.asyncio
    async def test_pipeline_skips_duplicates(self, empty_registry):
        """Should not re-insert already registered capabilities."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_fake_embed_doc):

            chain = build_capability_registration_chain()

            tools = [{"name": "add", "description": "adds numbers"}]
            ctx = Payload({
                "server_name": "s1",
                "server_tools": tools,
                "capability_registry": empty_registry,
            })

            # First run
            result1 = await chain.run(ctx)
            assert result1.get("registered_count") == 1

            # Second run — should skip
            result2 = await chain.run(ctx)
            assert result2.get("registered_count") == 0
            assert len(empty_registry.list_all()) == 1

    @pytest.mark.asyncio
    async def test_pipeline_empty_tools(self, empty_registry):
        """Should handle empty tools list gracefully."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_fake_embed_doc):

            chain = build_capability_registration_chain()
            ctx = Payload({
                "server_name": "s1",
                "server_tools": [],
                "capability_registry": empty_registry,
            })
            result = await chain.run(ctx)

            assert result.get("registered_count") == 0
