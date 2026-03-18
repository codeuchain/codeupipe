"""Tests for provider resolution in agent_session.

Verifies that _resolve_provider checks ApiKeyStore first,
then falls back to CopilotProvider.
"""

from __future__ import annotations

import pytest

from codeupipe.ai.providers.api_key_store import ApiKeyEntry, ApiKeyStore


class TestResolveProvider:
    """Test the _resolve_provider function."""

    @pytest.mark.unit
    def test_resolves_from_store(self, tmp_path, monkeypatch):
        """When a stored provider exists, returns OpenAICompatibleProvider."""
        from codeupipe.ai.pipelines.agent_session import _resolve_provider
        from codeupipe.ai.providers.openai_compat import OpenAICompatibleProvider

        store = ApiKeyStore(store_path=tmp_path / "keys.enc")
        entry = ApiKeyEntry(
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key="gsk-test",
            model="llama-3.3-70b-versatile",
        )
        store.save(entry)
        store.set_active("groq")

        monkeypatch.setattr(
            "codeupipe.ai.providers.api_key_store.ApiKeyStore",
            lambda *a, **kw: store,
        )

        provider = _resolve_provider()
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider._model == "llama-3.3-70b-versatile"
        assert provider._base_url == "https://api.groq.com/openai/v1"

    @pytest.mark.unit
    def test_fallback_to_copilot_when_empty(self, tmp_path, monkeypatch):
        """When no stored provider, falls back to CopilotProvider."""
        from codeupipe.ai.pipelines.agent_session import _resolve_provider

        store = ApiKeyStore(store_path=tmp_path / "keys.enc")
        monkeypatch.setattr(
            "codeupipe.ai.providers.api_key_store.ApiKeyStore",
            lambda *a, **kw: store,
        )

        provider = _resolve_provider()
        # Should be CopilotProvider (the fallback)
        assert type(provider).__name__ == "CopilotProvider"

    @pytest.mark.unit
    def test_fallback_on_store_error(self, monkeypatch):
        """If ApiKeyStore import/init fails, falls back to CopilotProvider."""
        from codeupipe.ai.pipelines.agent_session import _resolve_provider

        def _boom(*a, **kw):
            raise RuntimeError("store broken")

        monkeypatch.setattr(
            "codeupipe.ai.providers.api_key_store.ApiKeyStore",
            _boom,
        )

        provider = _resolve_provider()
        assert type(provider).__name__ == "CopilotProvider"

    @pytest.mark.unit
    def test_auto_resolve_single_provider(self, tmp_path, monkeypatch):
        """Single stored provider auto-resolves without set_active."""
        from codeupipe.ai.pipelines.agent_session import _resolve_provider
        from codeupipe.ai.providers.openai_compat import OpenAICompatibleProvider

        store = ApiKeyStore(store_path=tmp_path / "keys.enc")
        entry = ApiKeyEntry(
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4.1",
        )
        store.save(entry)
        # No set_active — should auto-resolve

        monkeypatch.setattr(
            "codeupipe.ai.providers.api_key_store.ApiKeyStore",
            lambda *a, **kw: store,
        )

        provider = _resolve_provider()
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider._model == "gpt-4.1"

    @pytest.mark.unit
    def test_extras_passed_to_provider(self, tmp_path, monkeypatch):
        """Extra config from entry is forwarded to provider kwargs."""
        from codeupipe.ai.pipelines.agent_session import _resolve_provider
        from codeupipe.ai.providers.openai_compat import OpenAICompatibleProvider

        store = ApiKeyStore(store_path=tmp_path / "keys.enc")
        entry = ApiKeyEntry(
            name="custom",
            base_url="http://localhost:11434/v1",
            api_key="",
            model="llama3",
            extras={"temperature": 0.3, "max_tokens": 2048},
        )
        store.save(entry)

        monkeypatch.setattr(
            "codeupipe.ai.providers.api_key_store.ApiKeyStore",
            lambda *a, **kw: store,
        )

        provider = _resolve_provider()
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider._temperature == 0.3
        assert provider._max_tokens == 2048
