"""Tests for the api-keys MCP server pure-function layer.

Follows the same pattern as test_mcp_manager.py — tests target
the pure functions, never the FastMCP transport layer.
"""

from __future__ import annotations

import pytest

from codeupipe.ai.providers.api_key_store import ApiKeyEntry, ApiKeyStore


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path):
    """Isolated ApiKeyStore backed by tmp_path."""
    return ApiKeyStore(store_path=tmp_path / "keys.enc")


@pytest.fixture()
def openai_entry():
    return ApiKeyEntry(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test-abc123",
        model="gpt-4.1",
    )


@pytest.fixture()
def groq_entry():
    return ApiKeyEntry(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key="gsk_test-xyz789",
        model="llama-3.3-70b-versatile",
    )


# ── Tests: save_api_key ──────────────────────────────────────────────


class TestSaveApiKey:
    """Pure-function save_api_key tool."""

    @pytest.mark.unit
    def test_save_new_key(self, store, openai_entry):
        from codeupipe.ai.servers.api_keys import save_api_key

        result = save_api_key(
            store,
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test-abc123",
            model="gpt-4.1",
        )
        assert result["saved"] is True
        assert result["name"] == "openai"
        assert result["replaced"] is False

    @pytest.mark.unit
    def test_save_replaces_existing(self, store, openai_entry):
        from codeupipe.ai.servers.api_keys import save_api_key

        store.save(openai_entry)
        result = save_api_key(
            store,
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-new-key",
            model="gpt-4.1-mini",
        )
        assert result["replaced"] is True
        assert store.get("openai").model == "gpt-4.1-mini"

    @pytest.mark.unit
    def test_save_with_extras(self, store):
        from codeupipe.ai.servers.api_keys import save_api_key

        result = save_api_key(
            store,
            name="custom",
            base_url="http://localhost:11434/v1",
            api_key="",
            model="llama3",
            extras='{"temperature": 0.7}',
        )
        assert result["saved"] is True
        entry = store.get("custom")
        assert entry.extras == {"temperature": 0.7}


# ── Tests: list_api_keys ─────────────────────────────────────────────


class TestListApiKeys:
    """Pure-function list_api_keys tool."""

    @pytest.mark.unit
    def test_empty_store(self, store):
        from codeupipe.ai.servers.api_keys import list_api_keys

        result = list_api_keys(store)
        assert result["keys"] == []
        assert result["count"] == 0

    @pytest.mark.unit
    def test_multiple_keys(self, store, openai_entry, groq_entry):
        from codeupipe.ai.servers.api_keys import list_api_keys

        store.save(openai_entry)
        store.save(groq_entry)
        result = list_api_keys(store)
        assert result["count"] == 2
        assert "openai" in result["keys"]
        assert "groq" in result["keys"]

    @pytest.mark.unit
    def test_includes_active_marker(self, store, openai_entry, groq_entry):
        from codeupipe.ai.servers.api_keys import list_api_keys

        store.save(openai_entry)
        store.save(groq_entry)
        store.set_active("groq")
        result = list_api_keys(store)
        assert result["active"] == "groq"


# ── Tests: remove_api_key ────────────────────────────────────────────


class TestRemoveApiKey:
    """Pure-function remove_api_key tool."""

    @pytest.mark.unit
    def test_remove_existing(self, store, openai_entry):
        from codeupipe.ai.servers.api_keys import remove_api_key

        store.save(openai_entry)
        result = remove_api_key(store, name="openai")
        assert result["removed"] is True
        assert store.get("openai") is None

    @pytest.mark.unit
    def test_remove_nonexistent(self, store):
        from codeupipe.ai.servers.api_keys import remove_api_key

        result = remove_api_key(store, name="nope")
        assert result["removed"] is False


# ── Tests: set_active_provider ────────────────────────────────────────


class TestSetActiveProvider:
    """Pure-function set_active_provider tool."""

    @pytest.mark.unit
    def test_set_valid(self, store, openai_entry):
        from codeupipe.ai.servers.api_keys import set_active_provider

        store.save(openai_entry)
        result = set_active_provider(store, name="openai")
        assert result["active"] == "openai"
        assert result["ok"] is True

    @pytest.mark.unit
    def test_set_nonexistent(self, store):
        from codeupipe.ai.servers.api_keys import set_active_provider

        result = set_active_provider(store, name="ghost")
        assert result["ok"] is False
        assert "error" in result


# ── Tests: get_active_provider ────────────────────────────────────────


class TestGetActiveProvider:
    """Pure-function get_active_provider tool."""

    @pytest.mark.unit
    def test_no_active(self, store):
        from codeupipe.ai.servers.api_keys import get_active_provider

        result = get_active_provider(store)
        assert result["active"] is None
        assert result["provider"] is None

    @pytest.mark.unit
    def test_with_active(self, store, openai_entry):
        from codeupipe.ai.servers.api_keys import get_active_provider

        store.save(openai_entry)
        store.set_active("openai")
        result = get_active_provider(store)
        assert result["active"] == "openai"
        assert result["provider"]["base_url"] == "https://api.openai.com/v1"
        assert result["provider"]["model"] == "gpt-4.1"

    @pytest.mark.unit
    def test_auto_resolve_single(self, store, openai_entry):
        from codeupipe.ai.servers.api_keys import get_active_provider

        store.save(openai_entry)
        result = get_active_provider(store)
        # auto-resolve: single provider
        assert result["provider"]["name"] == "openai"

    @pytest.mark.unit
    def test_redacts_api_key(self, store, openai_entry):
        from codeupipe.ai.servers.api_keys import get_active_provider

        store.save(openai_entry)
        store.set_active("openai")
        result = get_active_provider(store)
        # Full API key should never appear in tool output
        assert "sk-test-abc123" not in str(result)
        assert result["provider"]["api_key"].endswith("****")


# ── Tests: get_provider_details ───────────────────────────────────────


class TestGetProviderDetails:
    """Pure-function get_provider_details tool."""

    @pytest.mark.unit
    def test_existing(self, store, openai_entry):
        from codeupipe.ai.servers.api_keys import get_provider_details

        store.save(openai_entry)
        result = get_provider_details(store, name="openai")
        assert result["found"] is True
        assert result["provider"]["name"] == "openai"
        assert result["provider"]["base_url"] == "https://api.openai.com/v1"
        # Redacted
        assert "sk-test-abc123" not in str(result)

    @pytest.mark.unit
    def test_nonexistent(self, store):
        from codeupipe.ai.servers.api_keys import get_provider_details

        result = get_provider_details(store, name="nope")
        assert result["found"] is False
