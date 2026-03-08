"""
AuthHook — inject fresh OAuth2 credentials into pipeline runs.

Attaches to a pipeline as a Hook. Before each run, loads the
credential from the store (auto-refreshing if expired) and injects
it into the Payload so filters can read ``payload.get("access_token")``.
"""

from typing import Optional, TypeVar

from ..core.hook import Hook
from ..core.payload import Payload
from ..core.filter import Filter
from .credential import CredentialStore

__all__ = ["AuthHook"]

T = TypeVar("T")


class AuthHook(Hook):
    """Pipeline hook that injects OAuth credentials into every run.

    Before the pipeline starts (filter=None), loads the credential
    for the given provider from the store and inserts:
    - ``access_token``: Current (possibly refreshed) access token
    - ``token_type``: Token type (usually 'Bearer')
    - ``auth_provider``: Provider name

    Args:
        store: CredentialStore to load credentials from.
        provider: Provider name to look up (e.g. 'google', 'github').
        required: If True, raises RuntimeError when no valid credential found.
        token_key: Payload key for the access token (default: 'access_token').
    """

    def __init__(
        self,
        store: CredentialStore,
        provider: str,
        required: bool = True,
        token_key: str = "access_token",
    ):
        self._store = store
        self._provider = provider
        self._required = required
        self._token_key = token_key

    async def before(self, filter: Optional[Filter], payload: Payload[T]) -> None:
        """Inject credentials before the pipeline starts."""
        # Only inject at pipeline start (filter=None), not before each filter
        if filter is not None:
            return

        cred = self._store.get(self._provider)

        if cred is None or not cred.valid:
            if self._required:
                raise RuntimeError(
                    f"No valid credential for '{self._provider}'. "
                    f"Run: cup auth login {self._provider}"
                )
            return

        # Inject into payload via mutation on the internal dict.
        # Hook.before doesn't return payload, so we mutate _data directly.
        # This is the established hook pattern in codeupipe.
        payload._data[self._token_key] = cred.access_token
        payload._data["token_type"] = cred.token_type
        payload._data["auth_provider"] = cred.provider
