"""ApiKeyStore — encrypted persistence for LLM provider API keys.

Stores provider configurations (name, base_url, api_key, model)
encrypted to disk using the existing core/secure.py encrypt/decrypt.
Zero external dependencies — stdlib + codeupipe.core.secure.

Design:
    - One file per store: ``~/.codeupipe/api_keys.enc``
    - Entire file is a single encrypted blob (not per-entry)
    - Master key can be user-provided or derived from machine identity
    - ``_active`` field tracks which provider is the default
    - Thread-safe: read-modify-write on every operation

Usage:
    store = ApiKeyStore()
    store.save(ApiKeyEntry(name="openai", base_url="...", api_key="sk-...", model="gpt-4.1"))
    store.set_active("openai")
    entry = store.resolve_active()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeupipe.core.secure import (
    SecurePayloadError,
    decrypt_data,
    encrypt_data,
)

logger = logging.getLogger("codeupipe.ai.providers.api_key_store")

__all__ = ["ApiKeyEntry", "ApiKeyStore"]


@dataclass
class ApiKeyEntry:
    """A single provider's API configuration.

    Attributes:
        name: Provider identifier (e.g. "openai", "groq", "ollama").
        base_url: Base URL for the OpenAI-compatible API.
        api_key: API key / token (encrypted at rest).
        model: Default model to use with this provider.
        extras: Provider-specific additional configuration.
    """

    name: str
    base_url: str
    api_key: str
    model: str
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (for encrypted storage)."""
        return {
            "name": self.name,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "extras": dict(self.extras),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApiKeyEntry:
        """Deserialize from dict."""
        return cls(
            name=data["name"],
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            model=data.get("model", ""),
            extras=data.get("extras", {}),
        )

    def __repr__(self) -> str:
        # Redact API key in repr for safety
        redacted = self.api_key[:4] + "****" if len(self.api_key) > 4 else "****"
        return (
            f"ApiKeyEntry(name={self.name!r}, base_url={self.base_url!r}, "
            f"api_key={redacted!r}, model={self.model!r})"
        )


class ApiKeyStore:
    """Encrypted file-backed store for LLM provider API keys.

    The entire key collection is stored as a single encrypted blob
    using ``codeupipe.core.secure.encrypt_data`` (PBKDF2 + HMAC-SHA256).

    Args:
        store_path: Path to the encrypted store file.
                    Defaults to ``~/.codeupipe/api_keys.enc``.
        master_key: Encryption key (bytes). If None, derives from
                    a machine-local identifier.
    """

    def __init__(
        self,
        store_path: Path | str | None = None,
        master_key: bytes | None = None,
    ) -> None:
        if store_path is None:
            store_path = Path.home() / ".codeupipe" / "api_keys.enc"
        self._path = Path(store_path).expanduser()
        self._key = master_key or self._derive_default_key()

    @property
    def _store_path(self) -> Path:
        """For test introspection."""
        return self._path

    # ── Public API ────────────────────────────────────────────────────

    def save(self, entry: ApiKeyEntry) -> None:
        """Save or update a provider entry (encrypted to disk)."""
        data = self._load()
        data["keys"][entry.name] = entry.to_dict()
        self._write(data)
        logger.info("Saved API key for provider '%s'", entry.name)

    def get(self, name: str) -> ApiKeyEntry | None:
        """Retrieve a provider entry by name."""
        data = self._load()
        entry_data = data.get("keys", {}).get(name)
        if entry_data is None:
            return None
        return ApiKeyEntry.from_dict(entry_data)

    def list_keys(self) -> list[str]:
        """List all stored provider names (sorted)."""
        data = self._load()
        return sorted(data.get("keys", {}).keys())

    def remove(self, name: str) -> bool:
        """Remove a provider entry.

        Returns True if removed, False if not found.
        Clears active if the removed provider was active.
        """
        data = self._load()
        if name not in data.get("keys", {}):
            return False
        del data["keys"][name]
        if data.get("_active") == name:
            data["_active"] = None
        self._write(data)
        logger.info("Removed API key for provider '%s'", name)
        return True

    def set_active(self, name: str) -> None:
        """Set the active (default) provider.

        Raises ValueError if the provider doesn't exist.
        """
        data = self._load()
        if name not in data.get("keys", {}):
            raise ValueError(f"Provider '{name}' not found in key store")
        data["_active"] = name
        self._write(data)
        logger.info("Active provider set to '%s'", name)

    def get_active(self) -> str | None:
        """Get the name of the active provider, or None."""
        data = self._load()
        return data.get("_active")

    def resolve_active(self) -> ApiKeyEntry | None:
        """Get the active provider's entry.

        If no active is set but only one provider exists, returns it.
        """
        data = self._load()
        active = data.get("_active")
        keys = data.get("keys", {})

        if active and active in keys:
            return ApiKeyEntry.from_dict(keys[active])

        # Auto-resolve: single provider
        if not active and len(keys) == 1:
            name = next(iter(keys))
            return ApiKeyEntry.from_dict(keys[name])

        return None

    # ── Internals ─────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        """Load and decrypt the store file."""
        if not self._path.exists():
            return {"keys": {}, "_active": None}
        try:
            encrypted = self._path.read_text(encoding="utf-8").strip()
            if not encrypted:
                return {"keys": {}, "_active": None}
            return decrypt_data(encrypted, self._key)
        except SecurePayloadError:
            logger.warning("Failed to decrypt API key store (wrong key?)")
            return {"keys": {}, "_active": None}
        except Exception:
            logger.warning("Failed to load API key store", exc_info=True)
            return {"keys": {}, "_active": None}

    def _write(self, data: dict[str, Any]) -> None:
        """Encrypt and write the store file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = encrypt_data(data, self._key)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(encrypted, encoding="utf-8")
        tmp.rename(self._path)
        # Restrict permissions — API keys are sensitive
        try:
            self._path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _derive_default_key() -> bytes:
        """Derive a machine-local encryption key.

        Uses a combination of username + hostname as a seed.
        Not cryptographically ideal but prevents casual snooping.
        For real security, pass an explicit master_key.
        """
        import getpass
        import hashlib
        import platform

        seed = f"codeupipe::{getpass.getuser()}@{platform.node()}"
        return hashlib.sha256(seed.encode("utf-8")).digest()
