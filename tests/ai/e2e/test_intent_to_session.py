"""E2E test: Intent -> Session integration.

Exercises the full agent session lifecycle with discovery:
  1. Build agent session chain (includes DiscoverByIntentLink)
  2. Feed a prompt with a capability_registry attached
  3. Verify discovery runs as part of session setup
  4. Verify the full pipeline (register -> discover -> session)

Uses mocked embedder + mocked Copilot client, but real SQLite
registry, real chains, and real codeupipe orchestration.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.pipelines.agent_session import (
    build_agent_session_chain,
)
from codeupipe.ai.pipelines.capability_registration import (
    build_capability_registration_chain,
)
from codeupipe.ai.config import reset_settings
from codeupipe.ai.discovery.embedder import (
    SnowflakeArcticEmbedder,
)
from codeupipe.ai.discovery.registry import CapabilityRegistry

# -- Embedding fakes -----------------------------------------------

DOMAIN_VECTORS = {
    "math": (0, 100),
    "weather": (100, 200),
    "email": (200, 300),
}

_MATH_KW = [
    "add", "subtract", "math", "sum", "calculate", "number",
]
_WEATHER_KW = ["weather", "forecast", "temperature", "city"]
_EMAIL_KW = ["email", "send", "message", "recipient"]


def _domain_embedding(text: str) -> np.ndarray:
    """Fake embedding with semantic separation."""
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


_LINK_BASE = "codeupipe.ai.filters"


@contextmanager
def _patch_session_links():
    """Patch all agent-session links except discovery."""
    patches = {
        "register": patch(
            f"{_LINK_BASE}.register_servers"
            ".RegisterServersLink.call",
            new_callable=AsyncMock,
        ),
        "init_provider": patch(
            f"{_LINK_BASE}.init_provider"
            ".InitProviderLink.call",
            new_callable=AsyncMock,
        ),
        "agent_loop": patch(
            f"{_LINK_BASE}.loop.agent_loop"
            ".AgentLoopLink.call",
            new_callable=AsyncMock,
        ),
        "cleanup": patch(
            f"{_LINK_BASE}.session_cleanup"
            ".CleanupSessionLink.call",
            new_callable=AsyncMock,
        ),
    }
    mocks = {}
    for name, p in patches.items():
        mocks[name] = p.__enter__()
    try:
        yield mocks
    finally:
        for p in patches.values():
            p.__exit__(None, None, None)


@pytest.fixture(autouse=True)
def _clean():
    SnowflakeArcticEmbedder.reset()
    reset_settings()
    yield
    SnowflakeArcticEmbedder.reset()
    reset_settings()


@pytest.fixture
def registry_with_tools(tmp_path):
    """Registry pre-populated with tools."""
    import asyncio

    async def _populate():
        db = tmp_path / "session_test.db"
        registry = CapabilityRegistry(db)

        with _patch_embedder(query=False):
            chain = build_capability_registration_chain()
            await chain.run(Payload({
                "server_name": "calc-server",
                "server_tools": [
                    {
                        "name": "add_numbers",
                        "description": (
                            "adds two numbers"
                            " to calculate a sum"
                        ),
                    },
                    {
                        "name": "multiply",
                        "description": (
                            "multiplies numbers"
                            " together for math"
                        ),
                    },
                ],
                "capability_registry": registry,
            }))
            await chain.run(Payload({
                "server_name": "weather-server",
                "server_tools": [
                    {
                        "name": "get_forecast",
                        "description": (
                            "weather forecast"
                            " temperature for city"
                        ),
                    },
                ],
                "capability_registry": registry,
            }))

        return registry

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_populate())
    finally:
        loop.close()


@pytest.mark.e2e
class TestIntentToSession:
    """E2E: prompt -> session chain with discovery."""

    @pytest.mark.asyncio
    async def test_session_chain_discovers_capabilities(
        self, registry_with_tools,
    ):
        """Session chain discovers before prompt."""
        mock_hub = MagicMock()
        mock_hub.servers = {
            "calc-server": MagicMock(),
            "weather-server": MagicMock(),
        }

        mock_session = AsyncMock()
        mock_session.send_prompt = AsyncMock(
            return_value="42",
        )
        mock_session.__aenter__ = AsyncMock(
            return_value=mock_session,
        )
        mock_session.__aexit__ = AsyncMock(
            return_value=False,
        )

        mock_client = MagicMock()
        mock_client.create_session = MagicMock(
            return_value=mock_session,
        )

        with _patch_embedder(doc=False), \
             _patch_session_links() as mocks:

            async def pass_through(ctx):
                return ctx

            mocks["register"].side_effect = pass_through
            mocks["init_provider"].side_effect = (
                lambda ctx: ctx.insert(
                    "provider", mock_client,
                )
            )
            mocks["agent_loop"].side_effect = (
                lambda ctx: ctx.insert("response", "42")
            )
            mocks["cleanup"].side_effect = (
                lambda ctx: ctx.insert(
                    "cleaned_up", True,
                )
            )

            chain = build_agent_session_chain()
            ctx = Payload({
                "registry": mock_hub,
                "model": "gpt-4.1",
                "prompt": "calculate the sum of numbers",
                "capability_registry": registry_with_tools,
            })

            result = await chain.run(ctx)

            capabilities = result.get("capabilities")
            assert capabilities is not None
            names = [c.name for c in capabilities]
            assert (
                "add_numbers" in names
                or "multiply" in names
            )

    @pytest.mark.asyncio
    async def test_session_without_registry_passes_through(
        self,
    ):
        """No capability_registry -> discovery skipped."""
        mock_hub = MagicMock()
        mock_hub.servers = {}

        with _patch_session_links() as mocks:

            async def pass_through(ctx):
                return ctx

            mocks["register"].side_effect = pass_through
            mocks["init_provider"].side_effect = pass_through
            mocks["agent_loop"].side_effect = (
                lambda ctx: ctx.insert(
                    "response", "hello",
                )
            )
            mocks["cleanup"].side_effect = (
                lambda ctx: ctx.insert(
                    "cleaned_up", True,
                )
            )

            chain = build_agent_session_chain()
            ctx = Payload({
                "registry": mock_hub,
                "model": "gpt-4.1",
                "prompt": "just a normal prompt",
            })

            result = await chain.run(ctx)
            assert result.get("response") == "hello"
            assert result.get("capabilities") is None


@pytest.mark.e2e
class TestCLIDiscoverMode:
    """E2E: CLI --discover flag integration."""

    @pytest.mark.asyncio
    async def test_discover_prints_capabilities(
        self, registry_with_tools, capsys, tmp_path,
    ):
        """CLI discover prints matching tools."""
        from codeupipe.ai.entry.cli import (
            discover_capabilities,
        )

        db_path = str(tmp_path / "session_test.db")

        with _patch_embedder(doc=False), \
             patch(
                 "codeupipe.ai.config.get_settings",
             ) as mock_settings, \
             patch(
                 "codeupipe.ai.discovery.registry"
                 ".CapabilityRegistry",
                 return_value=registry_with_tools,
             ):
            mock_settings.return_value = MagicMock(
                registry_path=db_path,
            )

            await discover_capabilities(
                "calculate math sum numbers",
                verbose=False,
            )

            captured = capsys.readouterr()
            assert (
                "add_numbers" in captured.out
                or "multiply" in captured.out
            )
            assert (
                "matching capabilities"
                in captured.out.lower()
            )

    @pytest.mark.asyncio
    async def test_discover_empty_registry(
        self, tmp_path, capsys,
    ):
        """CLI discover empty registry -> no-match."""
        from codeupipe.ai.entry.cli import (
            discover_capabilities,
        )

        db = tmp_path / "empty.db"
        empty_registry = CapabilityRegistry(db)

        with _patch_embedder(doc=False), \
             patch(
                 "codeupipe.ai.config.get_settings",
             ) as mock_settings, \
             patch(
                 "codeupipe.ai.discovery.registry"
                 ".CapabilityRegistry",
                 return_value=empty_registry,
             ):
            mock_settings.return_value = MagicMock(
                registry_path=str(db),
            )

            await discover_capabilities(
                "anything", verbose=False,
            )

            captured = capsys.readouterr()
            assert "no matching" in captured.err.lower()
