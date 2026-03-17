"""E2E test: Register -> Discover flow.

Exercises the full lifecycle:
  1. Create a fresh registry
  2. Register server capabilities via CapabilityRegistrationChain
  3. Discover capabilities by intent via IntentDiscoveryChain
  4. Verify the correct tools are returned

Uses mocked embeddings (no real model download) but real SQLite
and real chain orchestration.
"""

from contextlib import contextmanager
from unittest.mock import patch

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.pipelines.capability_registration import (
    build_capability_registration_chain,
)
from codeupipe.ai.pipelines.intent_discovery import (
    build_intent_discovery_chain,
)
from codeupipe.ai.config import reset_settings
from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder
from codeupipe.ai.discovery.models import CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry

# -- Embedding fakes ------------------------------------------------

DOMAIN_VECTORS = {
    "math": (0, 100),
    "weather": (100, 200),
    "email": (200, 300),
}

_MATH_KW = ["add", "subtract", "math", "sum", "calculate", "number"]
_WEATHER_KW = ["weather", "forecast", "temperature", "city"]
_EMAIL_KW = ["email", "send", "message", "recipient"]


def _domain_embedding(text: str) -> np.ndarray:
    """Fake embedding with semantic domain separation."""
    vec = np.zeros(1024, dtype=np.float32)
    low = text.lower()

    if any(w in low for w in _MATH_KW):
        s, e = DOMAIN_VECTORS["math"]
        vec[s:e] = 1.0
    elif any(w in low for w in _WEATHER_KW):
        s, e = DOMAIN_VECTORS["weather"]
        vec[s:e] = 1.0
    elif any(w in low for w in _EMAIL_KW):
        s, e = DOMAIN_VECTORS["email"]
        vec[s:e] = 1.0
    else:
        vec[:50] = 0.1

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


@contextmanager
def _patch_embedder(*, doc=True, query=True):
    """Patch SnowflakeArcticEmbedder init + methods."""
    patches = [
        patch.object(
            SnowflakeArcticEmbedder, "__init__",
            return_value=None,
        ),
    ]
    if doc:
        patches.append(patch.object(
            SnowflakeArcticEmbedder, "embed_document",
            side_effect=_domain_embedding,
        ))
    if query:
        patches.append(patch.object(
            SnowflakeArcticEmbedder, "embed_query",
            side_effect=_domain_embedding,
        ))
    ctxs = [p.__enter__() for p in patches]
    try:
        yield ctxs
    finally:
        for p in patches:
            p.__exit__(None, None, None)


@pytest.fixture(autouse=True)
def _clean():
    SnowflakeArcticEmbedder.reset()
    reset_settings()
    yield
    SnowflakeArcticEmbedder.reset()
    reset_settings()


@pytest.fixture
def fresh_registry(tmp_path):
    """Create a fresh SQLite registry."""
    db = tmp_path / "e2e_test.db"
    return CapabilityRegistry(db)


@pytest.mark.e2e
class TestDiscoveryFlow:
    """End-to-end: register tools -> discover by intent."""

    @pytest.mark.asyncio
    async def test_register_then_discover_math(
        self, fresh_registry,
    ):
        """Register 3 tools, discover calculate sum -> math."""
        with _patch_embedder():
            reg_chain = build_capability_registration_chain()
            reg_ctx = Payload({
                "server_name": "multi-server",
                "server_tools": [
                    {
                        "name": "add_numbers",
                        "description": (
                            "adds two numbers"
                            " to calculate a sum"
                        ),
                    },
                    {
                        "name": "get_weather",
                        "description": (
                            "fetches weather"
                            " forecast for a city"
                        ),
                    },
                    {
                        "name": "send_email",
                        "description": (
                            "sends an email"
                            " to a recipient"
                        ),
                    },
                ],
                "capability_registry": fresh_registry,
            })
            reg_result = await reg_chain.run(reg_ctx)
            assert reg_result.get("registered_count") == 3

            disc_chain = build_intent_discovery_chain()
            disc_ctx = Payload({
                "intent": "calculate the sum of two numbers",
                "capability_registry": fresh_registry,
            })
            disc_result = await disc_chain.run(disc_ctx)

            capabilities = disc_result.get("capabilities")
            assert len(capabilities) > 0
            names = [c.name for c in capabilities]
            assert "add_numbers" in names

    @pytest.mark.asyncio
    async def test_register_then_discover_weather(
        self, fresh_registry,
    ):
        """Register tools, weather forecast -> weather."""
        with _patch_embedder():
            reg_chain = build_capability_registration_chain()
            reg_ctx = Payload({
                "server_name": "multi-server",
                "server_tools": [
                    {
                        "name": "add_numbers",
                        "description": "adds two numbers",
                    },
                    {
                        "name": "get_weather",
                        "description": (
                            "fetches weather forecast"
                            " temperature for a city"
                        ),
                    },
                    {
                        "name": "send_email",
                        "description": "sends an email",
                    },
                ],
                "capability_registry": fresh_registry,
            })
            await reg_chain.run(reg_ctx)

            disc_chain = build_intent_discovery_chain()
            disc_ctx = Payload({
                "intent": "what is the weather forecast",
                "capability_registry": fresh_registry,
            })
            disc_result = await disc_chain.run(disc_ctx)

            capabilities = disc_result.get("capabilities")
            names = [c.name for c in capabilities]
            assert "get_weather" in names

    @pytest.mark.asyncio
    async def test_discover_preserves_capability_metadata(
        self, fresh_registry,
    ):
        """Discovered capabilities keep original metadata."""
        with _patch_embedder():
            reg_chain = build_capability_registration_chain()
            reg_ctx = Payload({
                "server_name": "math-server",
                "server_tools": [
                    {
                        "name": "add_numbers",
                        "description": (
                            "adds numbers to calculate sum"
                        ),
                        "type": "tool",
                        "args_schema": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "int"},
                            },
                        },
                    },
                ],
                "capability_registry": fresh_registry,
            })
            await reg_chain.run(reg_ctx)

            disc_chain = build_intent_discovery_chain()
            disc_ctx = Payload({
                "intent": "calculate sum of numbers",
                "capability_registry": fresh_registry,
            })
            disc_result = await disc_chain.run(disc_ctx)

            caps = disc_result.get("capabilities")
            cap = next(
                c for c in caps if c.name == "add_numbers"
            )
            assert cap.server_name == "math-server"
            assert cap.capability_type == CapabilityType.TOOL
            assert cap.description == (
                "adds numbers to calculate sum"
            )

    @pytest.mark.asyncio
    async def test_discover_from_multiple_servers(
        self, fresh_registry,
    ):
        """Discover capabilities across multiple servers."""
        with _patch_embedder():
            reg_chain = build_capability_registration_chain()

            await reg_chain.run(Payload({
                "server_name": "math-server",
                "server_tools": [
                    {
                        "name": "add",
                        "description": (
                            "adds numbers to calculate sum"
                        ),
                    },
                ],
                "capability_registry": fresh_registry,
            }))

            await reg_chain.run(Payload({
                "server_name": "weather-server",
                "server_tools": [
                    {
                        "name": "forecast",
                        "description": (
                            "weather forecast"
                            " temperature for city"
                        ),
                    },
                ],
                "capability_registry": fresh_registry,
            }))

            assert len(fresh_registry.list_all()) == 2

            disc_chain = build_intent_discovery_chain()
            result = await disc_chain.run(Payload({
                "intent": "calculate math sum numbers",
                "capability_registry": fresh_registry,
            }))

            capabilities = result.get("capabilities")
            assert any(
                c.name == "add" for c in capabilities
            )

    @pytest.mark.asyncio
    async def test_empty_registry_returns_nothing(
        self, fresh_registry,
    ):
        """Discovery against empty registry -> empty list."""
        with _patch_embedder(doc=False):
            disc_chain = build_intent_discovery_chain()
            result = await disc_chain.run(Payload({
                "intent": "anything",
                "capability_registry": fresh_registry,
            }))

            assert result.get("capabilities") == []
