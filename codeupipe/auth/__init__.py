"""
codeupipe.auth: OAuth2 credential management for pipelines.

Provides browser-based OAuth2 flows, persistent token storage,
and automatic credential injection into pipeline runs.
Zero external dependencies — stdlib only.

Core types:
- Credential: Token container (access_token, refresh_token, expiry, scopes)
- CredentialStore: Persist + refresh credentials — file-backed JSON
- AuthProvider: Protocol for OAuth2 flows (authorize_url, exchange_code, refresh)
- AuthHook: Pipeline Hook — injects fresh tokens into Payload before each run

Built-in providers:
- GoogleOAuth: Google OAuth2 (Calendar, Drive, Gmail, etc.)
- GitHubOAuth: GitHub OAuth2 (repos, issues, actions, etc.)
"""

from .credential import Credential, CredentialStore
from .provider import AuthProvider, GoogleOAuth, GitHubOAuth
from .hook import AuthHook

__all__ = [
    "Credential",
    "CredentialStore",
    "AuthProvider",
    "GoogleOAuth",
    "GitHubOAuth",
    "AuthHook",
]
