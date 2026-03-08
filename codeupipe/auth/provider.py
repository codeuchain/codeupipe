"""
AuthProvider protocol and built-in OAuth2 providers.

AuthProvider defines the interface for any OAuth2 flow.
GoogleOAuth and GitHubOAuth are built-in implementations
that use stdlib urllib for all HTTP calls.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .credential import Credential

__all__ = ["AuthProvider", "GoogleOAuth", "GitHubOAuth"]


class AuthProvider(ABC):
    """Protocol for OAuth2 providers.

    Subclasses implement three methods:
    - authorize_url(): Build the consent URL for browser redirect
    - exchange_code(): Swap the auth code for tokens
    - refresh(): Use a refresh token to get a new access token
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g. 'google', 'github')."""

    @abstractmethod
    def authorize_url(self, redirect_uri: str, state: str) -> str:
        """Build the OAuth2 authorization URL.

        Args:
            redirect_uri: Local callback URL (e.g. http://localhost:PORT/callback).
            state: Random state parameter for CSRF protection.

        Returns:
            Full authorization URL to open in browser.
        """

    @abstractmethod
    def exchange_code(self, code: str, redirect_uri: str) -> Credential:
        """Exchange an authorization code for tokens.

        Args:
            code: Authorization code from the callback.
            redirect_uri: Must match the one used in authorize_url.

        Returns:
            Credential with access_token, refresh_token, expiry, scopes.
        """

    @abstractmethod
    def refresh(self, credential: Credential) -> Optional[Credential]:
        """Refresh an expired credential.

        Args:
            credential: Credential with a refresh_token.

        Returns:
            New Credential with updated access_token and expiry,
            or None if refresh is not possible.
        """


def _post_form(url: str, data: Dict[str, str]) -> Dict[str, Any]:
    """POST form-encoded data and return parsed JSON response."""
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Google OAuth2 ────────────────────────────────────────────


class GoogleOAuth(AuthProvider):
    """Google OAuth2 provider.

    Supports any Google API scope — Calendar, Drive, Gmail, etc.
    Uses Google's standard OAuth2 endpoints.

    Args:
        client_id: OAuth2 client ID from Google Cloud Console.
        client_secret: OAuth2 client secret.
        scopes: List of OAuth2 scopes to request.
    """

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        scopes: Optional[List[str]] = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = scopes or ["openid", "email", "profile"]

    @property
    def name(self) -> str:
        return "google"

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        params = urllib.parse.urlencode({
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self._scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        })
        return f"{self.AUTH_URL}?{params}"

    def exchange_code(self, code: str, redirect_uri: str) -> Credential:
        data = _post_form(self.TOKEN_URL, {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        return self._parse_token_response(data)

    def refresh(self, credential: Credential) -> Optional[Credential]:
        if not credential.refresh_token:
            return None
        data = _post_form(self.TOKEN_URL, {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": credential.refresh_token,
            "grant_type": "refresh_token",
        })
        refreshed = self._parse_token_response(data)
        # Google doesn't always return a new refresh_token — keep the old one
        if not refreshed.refresh_token:
            refreshed = Credential(
                provider=refreshed.provider,
                access_token=refreshed.access_token,
                refresh_token=credential.refresh_token,
                token_type=refreshed.token_type,
                expiry=refreshed.expiry,
                scopes=refreshed.scopes,
                extra=refreshed.extra,
            )
        return refreshed

    def _parse_token_response(self, data: Dict[str, Any]) -> Credential:
        expires_in = data.get("expires_in", 3600)
        return Credential(
            provider=self.name,
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            expiry=time.time() + int(expires_in),
            scopes=data.get("scope", "").split() if data.get("scope") else self._scopes,
            extra={k: v for k, v in data.items()
                   if k not in ("access_token", "refresh_token", "token_type", "expires_in", "scope")},
        )


# ── GitHub OAuth2 ────────────────────────────────────────────


class GitHubOAuth(AuthProvider):
    """GitHub OAuth2 provider.

    Supports standard GitHub OAuth app scopes — repo, user, etc.

    Args:
        client_id: OAuth App client ID from GitHub Developer Settings.
        client_secret: OAuth App client secret.
        scopes: List of GitHub scopes to request.
    """

    AUTH_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        scopes: Optional[List[str]] = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = scopes or ["repo", "user"]

    @property
    def name(self) -> str:
        return "github"

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        params = urllib.parse.urlencode({
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self._scopes),
            "state": state,
        })
        return f"{self.AUTH_URL}?{params}"

    def exchange_code(self, code: str, redirect_uri: str) -> Credential:
        data = _post_form(self.TOKEN_URL, {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        })
        if "error" in data:
            raise RuntimeError(
                f"GitHub OAuth error: {data.get('error_description', data['error'])}"
            )
        return Credential(
            provider=self.name,
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "bearer"),
            expiry=0,  # GitHub tokens don't expire (unless using GitHub Apps)
            scopes=data.get("scope", "").split(",") if data.get("scope") else self._scopes,
        )

    def refresh(self, credential: Credential) -> Optional[Credential]:
        # Standard GitHub OAuth apps don't support refresh tokens.
        # GitHub Apps with user-to-server tokens do — handle if refresh_token is present.
        if not credential.refresh_token:
            return None
        data = _post_form(self.TOKEN_URL, {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": credential.refresh_token,
            "grant_type": "refresh_token",
        })
        if "error" in data:
            return None
        expires_in = data.get("expires_in", 0)
        return Credential(
            provider=self.name,
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", credential.refresh_token),
            token_type=data.get("token_type", "bearer"),
            expiry=time.time() + int(expires_in) if expires_in else 0,
            scopes=data.get("scope", "").split(",") if data.get("scope") else credential.scopes,
        )
