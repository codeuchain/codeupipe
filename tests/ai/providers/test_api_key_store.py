"""RED PHASE — Tests for ApiKeyStore.

ApiKeyStore persists provider API keys encrypted to disk using
the existing core/secure.py encrypt_data/decrypt_data.  Each entry
holds a provider name, base_url, api_key, model, and extras.

Tests use tmp_path for filesystem isolation.
"""

import pytest

from codeupipe.ai.providers.api_key_store import (
    ApiKeyEntry,
    ApiKeyStore,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path) -> ApiKeyStore:
    """Fresh store backed by a temp directory."""
    return ApiKeyStore(
        store_path=tmp_path / "api_keys.enc",
        master_key=b"test-secret-key-for-unit-tests",
    )


@pytest.fixture()
def entry() -> ApiKeyEntry:
    """Sample OpenAI entry."""
    return ApiKeyEntry(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test-1234567890abcdef",
        model="gpt-4.1",
    )


@pytest.fixture()
def groq_entry() -> ApiKeyEntry:
    """Sample Groq entry."""
    return ApiKeyEntry(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key="gsk_test_key",
        model="llama-3.3-70b-versatile",
    )


# ── ApiKeyEntry ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestApiKeyEntry:
    """Tests for the ApiKeyEntry dataclass."""

    def test_create_entry(self, entry: ApiKeyEntry):
        assert entry.name == "openai"
        assert entry.base_url == "https://api.openai.com/v1"
        assert entry.api_key == "sk-test-1234567890abcdef"
        assert entry.model == "gpt-4.1"

    def test_to_dict_round_trip(self, entry: ApiKeyEntry):
        d = entry.to_dict()
        restored = ApiKeyEntry.from_dict(d)
        assert restored.name == entry.name
        assert restored.api_key == entry.api_key
        assert restored.base_url == entry.base_url
        assert restored.model == entry.model

    def test_extras_preserved(self):
        e = ApiKeyEntry(
            name="custom",
            base_url="http://localhost:11434/v1",
            api_key="",
            model="llama3",
            extras={"temperature": 0.7, "org_id": "org-abc"},
        )
        d = e.to_dict()
        restored = ApiKeyEntry.from_dict(d)
        assert restored.extras["temperature"] == 0.7
        assert restored.extras["org_id"] == "org-abc"

    def test_redacted_repr(self, entry: ApiKeyEntry):
        """repr should NOT expose the full api_key."""
        r = repr(entry)
        assert "sk-test-1234567890abcdef" not in r
        assert "sk-te" in r or "****" in r or "openai" in r


# ── Save / Get ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSaveAndGet:
    """Tests for save + get cycle."""

    def test_save_and_get(self, store: ApiKeyStore, entry: ApiKeyEntry):
        store.save(entry)
        retrieved = store.get("openai")
        assert retrieved is not None
        assert retrieved.name == "openai"
        assert retrieved.api_key == "sk-test-1234567890abcdef"
        assert retrieved.base_url == "https://api.openai.com/v1"

    def test_get_nonexistent_returns_none(self, store: ApiKeyStore):
        assert store.get("ghost") is None

    def test_save_overwrites_existing(self, store: ApiKeyStore, entry: ApiKeyEntry):
        store.save(entry)
        updated = ApiKeyEntry(
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-new-key",
            model="gpt-4.1-mini",
        )
        store.save(updated)
        retrieved = store.get("openai")
        assert retrieved.api_key == "sk-new-key"
        assert retrieved.model == "gpt-4.1-mini"

    def test_multiple_providers(
        self, store: ApiKeyStore, entry: ApiKeyEntry, groq_entry: ApiKeyEntry,
    ):
        store.save(entry)
        store.save(groq_entry)
        assert store.get("openai") is not None
        assert store.get("groq") is not None
        assert store.get("openai").api_key != store.get("groq").api_key


# ── List ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestList:
    """Tests for list_keys."""

    def test_list_empty(self, store: ApiKeyStore):
        assert store.list_keys() == []

    def test_list_multiple(
        self, store: ApiKeyStore, entry: ApiKeyEntry, groq_entry: ApiKeyEntry,
    ):
        store.save(entry)
        store.save(groq_entry)
        names = store.list_keys()
        assert set(names) == {"openai", "groq"}

    def test_list_returns_sorted(
        self, store: ApiKeyStore, entry: ApiKeyEntry, groq_entry: ApiKeyEntry,
    ):
        store.save(entry)
        store.save(groq_entry)
        assert store.list_keys() == ["groq", "openai"]


# ── Remove ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRemove:
    """Tests for remove."""

    def test_remove_existing(self, store: ApiKeyStore, entry: ApiKeyEntry):
        store.save(entry)
        assert store.remove("openai") is True
        assert store.get("openai") is None

    def test_remove_nonexistent(self, store: ApiKeyStore):
        assert store.remove("ghost") is False


# ── Encryption ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEncryption:
    """Tests verifying API keys are encrypted on disk."""

    def test_file_is_encrypted(self, store: ApiKeyStore, entry: ApiKeyEntry):
        """The stored file should not contain the raw API key."""
        store.save(entry)
        raw = store._path.read_text(encoding="utf-8")
        assert "sk-test-1234567890abcdef" not in raw
        assert raw.startswith("cup_enc:")

    def test_wrong_key_cannot_decrypt(self, store: ApiKeyStore, entry: ApiKeyEntry, tmp_path):
        """A store with a different master key cannot read the data."""
        store.save(entry)
        wrong_store = ApiKeyStore(
            store_path=tmp_path / "api_keys.enc",
            master_key=b"totally-different-key",
        )
        # Should return None or raise — NOT return the key
        result = wrong_store.get("openai")
        assert result is None


# ── Active Provider ───────────────────────────────────────────────────


@pytest.mark.unit
class TestActiveProvider:
    """Tests for set_active / get_active provider."""

    def test_set_and_get_active(self, store: ApiKeyStore, entry: ApiKeyEntry):
        store.save(entry)
        store.set_active("openai")
        assert store.get_active() == "openai"

    def test_get_active_default_none(self, store: ApiKeyStore):
        assert store.get_active() is None

    def test_set_active_nonexistent_raises(self, store: ApiKeyStore):
        with pytest.raises(ValueError, match="not found"):
            store.set_active("ghost")

    def test_active_persists_across_loads(self, store: ApiKeyStore, entry: ApiKeyEntry, tmp_path):
        """Active provider persists after creating a new store instance."""
        store.save(entry)
        store.set_active("openai")
        store2 = ApiKeyStore(
            store_path=tmp_path / "api_keys.enc",
            master_key=b"test-secret-key-for-unit-tests",
        )
        assert store2.get_active() == "openai"

    def test_remove_active_clears_it(self, store: ApiKeyStore, entry: ApiKeyEntry):
        store.save(entry)
        store.set_active("openai")
        store.remove("openai")
        assert store.get_active() is None


# ── Resolve Active Entry ──────────────────────────────────────────────


@pytest.mark.unit
class TestResolveActive:
    """Tests for resolve_active convenience."""

    def test_resolve_active_entry(self, store: ApiKeyStore, entry: ApiKeyEntry):
        store.save(entry)
        store.set_active("openai")
        resolved = store.resolve_active()
        assert resolved is not None
        assert resolved.name == "openai"
        assert resolved.api_key == "sk-test-1234567890abcdef"

    def test_resolve_no_active_returns_none(self, store: ApiKeyStore):
        assert store.resolve_active() is None

    def test_resolve_first_if_single_provider(self, store: ApiKeyStore, entry: ApiKeyEntry):
        """If only one key is saved and none active, resolve returns it."""
        store.save(entry)
        resolved = store.resolve_active()
        assert resolved is not None
        assert resolved.name == "openai"
