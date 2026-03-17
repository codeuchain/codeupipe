"""Shared fixtures for agent loop E2E tests.

Provides mock session, mock provider, embedder patches, and pre-populated
registries that the E2E agent loop tests share.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.pipelines.capability_registration import (
    build_capability_registration_chain,
)
from codeupipe.ai.config import reset_settings
from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder
from codeupipe.ai.discovery.registry import CapabilityRegistry
from codeupipe.ai.hub.io_wrapper import HubIOWrapper
from codeupipe.ai.hub.registry import ServerRegistry
from codeupipe.ai.loop.context_budget import ContextBudget, ContextBudgetTracker
from codeupipe.ai.loop.notifications import (
    Notification,
    NotificationPriority,
    NotificationQueue,
    NotificationSource,
)
from codeupipe.ai.loop.session_store import SessionStore
from codeupipe.ai.loop.state import AgentState
from codeupipe.ai.hooks.audit_producer import NoopAuditSink
from codeupipe.ai.providers.base import ModelResponse


# ── Embedding fakes ──────────────────────────────────────────────────

DOMAIN_VECTORS = {
    "math": (0, 100),
    "auth": (100, 200),
    "testing": (200, 300),
    "deploy": (300, 400),
}

_KW_MAP = {
    "math": ["add", "subtract", "math", "sum", "calculate", "number"],
    "auth": ["auth", "login", "password", "token", "authenticate", "permission"],
    "testing": ["test", "verify", "assert", "tdd", "coverage", "unit"],
    "deploy": ["deploy", "release", "ship", "production", "infra", "ci"],
}


def fake_embedding(text: str) -> np.ndarray:
    """Fake embedding with semantic domain separation."""
    vec = np.zeros(1024, dtype=np.float32)
    low = text.lower()

    for domain, keywords in _KW_MAP.items():
        if any(w in low for w in keywords):
            s, e = DOMAIN_VECTORS[domain]
            vec[s:e] = 1.0
            break
    else:
        vec[:50] = 0.1

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


@contextmanager
def patch_embedder():
    """Patch SnowflakeArcticEmbedder everywhere."""
    with (
        patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None),
        patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=fake_embedding),
        patch.object(SnowflakeArcticEmbedder, "embed_query", side_effect=fake_embedding),
    ):
        yield


# ── Mock session (simulates Copilot SDK send_and_wait) ───────────────


@dataclass
class FakeSessionEvent:
    """Simulates a Copilot SDK SessionEvent."""

    data: Any = None


@dataclass
class FakeSessionData:
    """Simulates the data payload of a SessionEvent."""

    content: str | None = None
    tool_results: list[dict] | None = None


class FakeSession:
    """Mock session that replays scripted responses.

    Usage:
        session = FakeSession([
            {"content": "Let me think..."},
            {"content": "Done!", "tool_results": [...]},
            {"content": "All finished."},
        ])

    Each call to send_and_wait pops the next response.
    If responses exhausted, returns empty content (triggers done).
    """

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self._call_log: list[dict] = []

    async def send_and_wait(self, payload: dict) -> FakeSessionEvent:
        self._call_log.append(payload)
        if self._responses:
            resp = self._responses.pop(0)
            data = FakeSessionData(
                content=resp.get("content"),
                tool_results=resp.get("tool_results"),
            )
            return FakeSessionEvent(data=data)
        return FakeSessionEvent(data=FakeSessionData(content=None))

    @property
    def call_log(self) -> list[dict]:
        return list(self._call_log)

    @property
    def call_count(self) -> int:
        return len(self._call_log)


class FakeProvider:
    """Mock provider that replays scripted responses.

    Wraps FakeSession behind the LanguageModelProvider interface.
    Use this instead of FakeSession in tests that go through the
    turn chain (which now uses LanguageModelLink, not SendTurnLink).

    Usage:
        provider = FakeProvider([
            {"content": "Let me think..."},
            {"content": "Done!", "tool_results": [...]},
        ])
        ctx = Payload({"provider": provider, "prompt": "hello"})
    """

    def __init__(self, responses: list[dict]) -> None:
        self._session = FakeSession(responses)
        self._started = False

    async def start(self, **kwargs: Any) -> None:
        self._started = True

    async def send(self, prompt: str) -> ModelResponse:
        event = await self._session.send_and_wait({"prompt": prompt})
        content = None
        tool_results: list[dict] = []

        if event and event.data:
            content = event.data.content
            if event.data.tool_results:
                tool_results = [
                    r for r in event.data.tool_results if isinstance(r, dict)
                ]

        return ModelResponse(
            content=content,
            tool_results=tuple(tool_results),
            raw=event,
        )

    async def stop(self) -> None:
        self._started = False

    @property
    def call_log(self) -> list[dict]:
        return self._session.call_log

    @property
    def call_count(self) -> int:
        return self._session.call_count


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_singletons():
    """Reset singletons between tests."""
    SnowflakeArcticEmbedder.reset()
    reset_settings()
    yield
    SnowflakeArcticEmbedder.reset()
    reset_settings()


@pytest.fixture
def fresh_registry(tmp_path):
    """Empty SQLite registry."""
    db = tmp_path / "e2e_agent.db"
    return CapabilityRegistry(db)


@pytest.fixture
def populated_registry(tmp_path):
    """Registry pre-populated with tools across domains."""

    async def _populate():
        db = tmp_path / "e2e_agent_pop.db"
        registry = CapabilityRegistry(db)

        with patch_embedder():
            chain = build_capability_registration_chain()
            await chain.run(Payload({
                "server_name": "math-server",
                "server_tools": [
                    {"name": "add_numbers", "description": "adds numbers to calculate a math sum"},
                    {"name": "multiply", "description": "multiplies math numbers together"},
                ],
                "capability_registry": registry,
            }))
            await chain.run(Payload({
                "server_name": "auth-server",
                "server_tools": [
                    {"name": "check_token", "description": "validates an auth token for login permission"},
                    {"name": "create_user", "description": "creates a user account with password and auth"},
                ],
                "capability_registry": registry,
            }))
            await chain.run(Payload({
                "server_name": "test-server",
                "server_tools": [
                    {"name": "run_tests", "description": "runs unit test suite with coverage and assert verification"},
                ],
                "capability_registry": registry,
            }))

        return registry

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_populate())
    finally:
        loop.close()


@pytest.fixture
def notification_queue():
    """Fresh notification queue."""
    return NotificationQueue()


@pytest.fixture
def hub_io(notification_queue):
    """HubIOWrapper with mock server registry."""
    return HubIOWrapper(
        server_registry=ServerRegistry(),
        notification_queue=notification_queue,
        context_budget=128_000,
    )


@pytest.fixture
def session_store(tmp_path):
    """In-memory session store."""
    return SessionStore(":memory:")


@pytest.fixture
def noop_sink():
    """NoopAuditSink for testing audit pipeline."""
    return NoopAuditSink()


@pytest.fixture
def budget_tracker():
    """ContextBudgetTracker with small budget for testing revision."""
    budget = ContextBudget(
        total_budget=1000,
        revision_threshold=0.5,
        min_turns_kept=2,
    )
    return ContextBudgetTracker(budget)
