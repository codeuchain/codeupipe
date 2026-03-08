"""
Credential and CredentialStore — token lifecycle management.

Credential is an immutable snapshot of OAuth2 tokens.
CredentialStore persists credentials to disk (JSON) and
auto-refreshes expired tokens via the associated AuthProvider.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = ["Credential", "CredentialStore"]

# Buffer (seconds) before actual expiry to trigger refresh
_EXPIRY_BUFFER = 300  # 5 minutes


class Credential:
    """Immutable OAuth2 credential snapshot.

    Attributes:
        provider: Provider name (e.g. 'google', 'github').
        access_token: Current access token.
        refresh_token: Long-lived refresh token (may be None for some flows).
        token_type: Token type (usually 'Bearer').
        expiry: Unix timestamp when access_token expires (0 = no expiry).
        scopes: List of granted scopes.
        extra: Provider-specific metadata.
    """

    __slots__ = (
        "provider", "access_token", "refresh_token", "token_type",
        "expiry", "scopes", "extra",
    )

    def __init__(
        self,
        provider: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_type: str = "Bearer",
        expiry: float = 0,
        scopes: Optional[list] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.provider = provider
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_type = token_type
        self.expiry = expiry
        self.scopes = list(scopes) if scopes else []
        self.extra = dict(extra) if extra else {}

    @property
    def expired(self) -> bool:
        """True if the access token has expired (or will in the next 5 min)."""
        if self.expiry == 0:
            return False  # no expiry set
        return time.time() >= (self.expiry - _EXPIRY_BUFFER)

    @property
    def valid(self) -> bool:
        """True if we have a non-empty, non-expired access token."""
        return bool(self.access_token) and not self.expired

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "provider": self.provider,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expiry": self.expiry,
            "scopes": self.scopes,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Credential":
        """Deserialize from dict."""
        return cls(
            provider=data["provider"],
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            expiry=data.get("expiry", 0),
            scopes=data.get("scopes", []),
            extra=data.get("extra", {}),
        )

    def __repr__(self) -> str:
        status = "valid" if self.valid else "expired"
        return f"Credential(provider={self.provider!r}, status={status})"


class CredentialStore:
    """File-backed credential store with auto-refresh.

    Stores credentials as JSON keyed by provider name.
    On ``get()``, checks token expiry and auto-refreshes via
    the associated AuthProvider if a refresh_token is available.

    Args:
        path: Path to the JSON credentials file.
              Defaults to ``~/.codeupipe/credentials.json``.
    """

    def __init__(self, path: Optional[str] = None):
        if path is None:
            path = str(Path.home() / ".codeupipe" / "credentials.json")
        self._path = Path(path).expanduser()
        self._providers: Dict[str, Any] = {}  # name → AuthProvider instance

    @property
    def path(self) -> Path:
        """Resolved path to the credentials file."""
        return self._path

    def register_provider(self, name: str, provider: Any) -> None:
        """Associate an AuthProvider with a provider name for auto-refresh."""
        self._providers[name] = provider

    def save(self, credential: "Credential") -> None:
        """Persist a credential to disk."""
        store = self._load_all()
        store[credential.provider] = credential.to_dict()
        self._write_all(store)

    def get(self, provider: str, auto_refresh: bool = True) -> Optional["Credential"]:
        """Load a credential, auto-refreshing if expired.

        Args:
            provider: Provider name (e.g. 'google', 'github').
            auto_refresh: If True and the token is expired, attempt refresh.

        Returns:
            Credential if found (possibly refreshed), None if not stored.
        """
        store = self._load_all()
        data = store.get(provider)
        if data is None:
            return None

        cred = Credential.from_dict(data)

        if cred.expired and auto_refresh and cred.refresh_token:
            refreshed = self._try_refresh(cred)
            if refreshed is not None:
                cred = refreshed

        return cred

    def remove(self, provider: str) -> bool:
        """Remove a credential from the store.

        Returns:
            True if a credential was removed, False if not found.
        """
        store = self._load_all()
        if provider not in store:
            return False
        del store[provider]
        self._write_all(store)
        return True

    def list_providers(self) -> list:
        """List all stored provider names."""
        store = self._load_all()
        return sorted(store.keys())

    def _try_refresh(self, cred: "Credential") -> Optional["Credential"]:
        """Attempt to refresh an expired credential via its provider."""
        prov = self._providers.get(cred.provider)
        if prov is None:
            return None
        try:
            refreshed = prov.refresh(cred)
            if refreshed is not None:
                self.save(refreshed)
            return refreshed
        except Exception:
            return None

    def _load_all(self) -> Dict[str, Any]:
        """Load the entire credentials file."""
        if not self._path.exists():
            return {}
        try:
            text = self._path.read_text(encoding="utf-8")
            return json.loads(text) if text.strip() else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_all(self, store: Dict[str, Any]) -> None:
        """Write the entire credentials file atomically."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write to temp then rename for atomic writes
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(store, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.rename(self._path)
        # Restrict permissions — credentials are sensitive
        try:
            self._path.chmod(0o600)
        except OSError:
            pass  # Windows or restrictive FS — best effort
