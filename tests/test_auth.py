"""Tests for codeupipe.auth — Credential, CredentialStore, AuthHook, providers, CLI.

Covers:
- Credential: creation, serialization, expiry, validity
- CredentialStore: save, get, remove, list, auto-refresh
- AuthProvider: GoogleOAuth and GitHubOAuth URL generation + token parsing
- AuthHook: credential injection into pipeline payload
- OAuth callback server: code capture, state validation, error handling
- CLI: cup auth login/status/revoke/list
"""

import asyncio
import json
import os
import secrets
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from codeupipe.core.payload import Payload
from codeupipe.core.pipeline import Pipeline
from codeupipe.core.filter import Filter
from codeupipe.auth.credential import Credential, CredentialStore
from codeupipe.auth.provider import AuthProvider, GoogleOAuth, GitHubOAuth
from codeupipe.auth.hook import AuthHook


# ── Helpers ──────────────────────────────────────────────────

class EchoFilter(Filter):
    """Filter that echoes a payload key for test verification."""
    async def call(self, payload: Payload) -> Payload:
        token = payload.get("access_token", "none")
        return payload.insert("echo_token", token)


class _FakeProvider(AuthProvider):
    """Minimal test provider."""

    @property
    def name(self):
        return "fake"

    def authorize_url(self, redirect_uri, state):
        return f"https://fake.test/auth?state={state}&redirect_uri={redirect_uri}"

    def exchange_code(self, code, redirect_uri):
        return Credential(
            provider="fake",
            access_token=f"access_{code}",
            refresh_token=f"refresh_{code}",
            expiry=time.time() + 3600,
            scopes=["read"],
        )

    def refresh(self, credential):
        return Credential(
            provider="fake",
            access_token="refreshed_token",
            refresh_token=credential.refresh_token,
            expiry=time.time() + 3600,
            scopes=credential.scopes,
        )


# ── Credential Tests ─────────────────────────────────────────


class TestCredential:
    """Credential is a token container with expiry tracking."""

    def test_create_credential(self):
        """Basic credential creation stores all fields."""
        cred = Credential(
            provider="google",
            access_token="abc123",
            refresh_token="ref456",
            expiry=time.time() + 3600,
            scopes=["email", "calendar"],
        )
        assert cred.provider == "google"
        assert cred.access_token == "abc123"
        assert cred.refresh_token == "ref456"
        assert cred.scopes == ["email", "calendar"]

    def test_valid_credential(self):
        """A credential with future expiry is valid."""
        cred = Credential(
            provider="google",
            access_token="abc",
            expiry=time.time() + 7200,  # 2 hours from now
        )
        assert cred.valid is True
        assert cred.expired is False

    def test_expired_credential(self):
        """A credential with past expiry is expired."""
        cred = Credential(
            provider="google",
            access_token="abc",
            expiry=time.time() - 100,  # expired 100s ago
        )
        assert cred.valid is False
        assert cred.expired is True

    def test_expiry_buffer(self):
        """Credentials expiring within 5 minutes are considered expired."""
        cred = Credential(
            provider="google",
            access_token="abc",
            expiry=time.time() + 60,  # 1 minute from now (within buffer)
        )
        assert cred.expired is True

    def test_no_expiry_always_valid(self):
        """Credentials with expiry=0 never expire (e.g. GitHub tokens)."""
        cred = Credential(provider="github", access_token="abc", expiry=0)
        assert cred.valid is True
        assert cred.expired is False

    def test_empty_token_invalid(self):
        """A credential with empty access_token is invalid."""
        cred = Credential(provider="github", access_token="", expiry=0)
        assert cred.valid is False

    def test_serialize_round_trip(self):
        """Credential serializes to dict and deserializes back."""
        original = Credential(
            provider="google",
            access_token="tok",
            refresh_token="ref",
            token_type="Bearer",
            expiry=1234567890.0,
            scopes=["email"],
            extra={"id_token": "jwt123"},
        )
        data = original.to_dict()
        restored = Credential.from_dict(data)

        assert restored.provider == original.provider
        assert restored.access_token == original.access_token
        assert restored.refresh_token == original.refresh_token
        assert restored.expiry == original.expiry
        assert restored.scopes == original.scopes
        assert restored.extra == original.extra

    def test_repr(self):
        """Repr shows provider and status."""
        cred = Credential(provider="github", access_token="abc", expiry=0)
        assert "github" in repr(cred)
        assert "valid" in repr(cred)

    def test_defaults(self):
        """Default values for optional fields."""
        cred = Credential(provider="test", access_token="tok")
        assert cred.refresh_token is None
        assert cred.token_type == "Bearer"
        assert cred.expiry == 0
        assert cred.scopes == []
        assert cred.extra == {}


# ── CredentialStore Tests ─────────────────────────────────────


class TestCredentialStore:
    """CredentialStore persists credentials to disk and auto-refreshes."""

    def test_save_and_load(self, tmp_path):
        """Save a credential and load it back."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        cred = Credential(
            provider="google",
            access_token="abc",
            refresh_token="ref",
            expiry=time.time() + 3600,
            scopes=["email"],
        )
        store.save(cred)

        loaded = store.get("google")
        assert loaded is not None
        assert loaded.access_token == "abc"
        assert loaded.provider == "google"

    def test_get_missing_returns_none(self, tmp_path):
        """Getting a non-existent provider returns None."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        assert store.get("nonexistent") is None

    def test_list_providers(self, tmp_path):
        """List returns all stored provider names."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        store.save(Credential(provider="google", access_token="a"))
        store.save(Credential(provider="github", access_token="b"))

        providers = store.list_providers()
        assert providers == ["github", "google"]

    def test_remove_credential(self, tmp_path):
        """Remove deletes a specific provider."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        store.save(Credential(provider="google", access_token="abc"))

        assert store.remove("google") is True
        assert store.get("google") is None

    def test_remove_nonexistent_returns_false(self, tmp_path):
        """Removing a non-existent provider returns False."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        assert store.remove("nope") is False

    def test_auto_refresh_on_expired(self, tmp_path):
        """Expired credentials are auto-refreshed via registered provider."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        provider = _FakeProvider()
        store.register_provider("fake", provider)

        expired = Credential(
            provider="fake",
            access_token="old_token",
            refresh_token="ref_token",
            expiry=time.time() - 1000,  # expired
        )
        store.save(expired)

        loaded = store.get("fake", auto_refresh=True)
        assert loaded is not None
        assert loaded.access_token == "refreshed_token"

    def test_no_refresh_without_provider(self, tmp_path):
        """Expired creds without a registered provider stay expired."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        expired = Credential(
            provider="google",
            access_token="old",
            refresh_token="ref",
            expiry=time.time() - 1000,
        )
        store.save(expired)

        loaded = store.get("google", auto_refresh=True)
        assert loaded is not None
        assert loaded.access_token == "old"  # wasn't refreshed

    def test_no_refresh_without_refresh_token(self, tmp_path):
        """Expired creds without a refresh_token can't be refreshed."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        store.register_provider("fake", _FakeProvider())
        expired = Credential(
            provider="fake",
            access_token="old",
            refresh_token=None,
            expiry=time.time() - 1000,
        )
        store.save(expired)

        loaded = store.get("fake", auto_refresh=True)
        assert loaded is not None
        assert loaded.access_token == "old"

    def test_auto_refresh_disabled(self, tmp_path):
        """auto_refresh=False skips refresh even if expired."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        store.register_provider("fake", _FakeProvider())
        expired = Credential(
            provider="fake",
            access_token="old",
            refresh_token="ref",
            expiry=time.time() - 1000,
        )
        store.save(expired)

        loaded = store.get("fake", auto_refresh=False)
        assert loaded.access_token == "old"

    def test_default_path(self):
        """Default path is ~/.codeupipe/credentials.json."""
        store = CredentialStore()
        assert store.path == Path.home() / ".codeupipe" / "credentials.json"

    def test_corrupted_file_returns_empty(self, tmp_path):
        """Corrupted JSON file is handled gracefully."""
        creds_file = tmp_path / "creds.json"
        creds_file.write_text("not json at all!")
        store = CredentialStore(str(creds_file))
        assert store.get("anything") is None
        assert store.list_providers() == []

    def test_multiple_providers(self, tmp_path):
        """Multiple providers coexist in the same store file."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        store.save(Credential(provider="google", access_token="g_tok"))
        store.save(Credential(provider="github", access_token="gh_tok"))

        assert store.get("google").access_token == "g_tok"
        assert store.get("github").access_token == "gh_tok"

    def test_overwrite_credential(self, tmp_path):
        """Saving again for same provider overwrites."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        store.save(Credential(provider="google", access_token="old"))
        store.save(Credential(provider="google", access_token="new"))

        loaded = store.get("google")
        assert loaded.access_token == "new"

    def test_file_permissions(self, tmp_path):
        """Credentials file has 600 permissions (owner-only)."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        store.save(Credential(provider="google", access_token="secret"))

        mode = oct(store.path.stat().st_mode)[-3:]
        assert mode == "600"


# ── AuthProvider Tests ────────────────────────────────────────


class TestGoogleOAuth:
    """GoogleOAuth generates correct URLs and parses token responses."""

    def test_name(self):
        p = GoogleOAuth("cid", "csecret")
        assert p.name == "google"

    def test_authorize_url_contains_required_params(self):
        p = GoogleOAuth("my_client_id", "secret", scopes=["email", "calendar"])
        url = p.authorize_url("http://localhost:8080/callback", "random_state")

        assert "my_client_id" in url
        assert "random_state" in url
        assert "email" in url
        assert "calendar" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url
        assert "response_type=code" in url
        assert url.startswith("https://accounts.google.com")

    def test_authorize_url_redirect_uri(self):
        p = GoogleOAuth("cid", "csecret")
        url = p.authorize_url("http://localhost:9999/callback", "state1")
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        assert params["redirect_uri"] == ["http://localhost:9999/callback"]

    def test_default_scopes(self):
        p = GoogleOAuth("cid", "csecret")
        url = p.authorize_url("http://localhost:8080/callback", "s")
        assert "openid" in url
        assert "email" in url
        assert "profile" in url

    @patch("codeupipe.auth.provider._post_form")
    def test_exchange_code(self, mock_post):
        """exchange_code parses Google's token response into a Credential."""
        mock_post.return_value = {
            "access_token": "ya29.abc",
            "refresh_token": "1//ref",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "email profile",
            "id_token": "jwt.stuff",
        }
        p = GoogleOAuth("cid", "csecret")
        cred = p.exchange_code("auth_code", "http://localhost:8080/callback")

        assert cred.provider == "google"
        assert cred.access_token == "ya29.abc"
        assert cred.refresh_token == "1//ref"
        assert cred.token_type == "Bearer"
        assert cred.expiry > time.time()
        assert "email" in cred.scopes
        assert cred.extra.get("id_token") == "jwt.stuff"

    @patch("codeupipe.auth.provider._post_form")
    def test_refresh_preserves_refresh_token(self, mock_post):
        """Google refresh doesn't always return new refresh_token — keep the old one."""
        mock_post.return_value = {
            "access_token": "ya29.new",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "email",
        }
        p = GoogleOAuth("cid", "csecret")
        old = Credential(
            provider="google",
            access_token="ya29.old",
            refresh_token="1//my_refresh",
            expiry=time.time() - 100,
        )
        refreshed = p.refresh(old)

        assert refreshed.access_token == "ya29.new"
        assert refreshed.refresh_token == "1//my_refresh"  # preserved

    def test_refresh_no_refresh_token(self):
        """Refresh returns None when no refresh_token exists."""
        p = GoogleOAuth("cid", "csecret")
        cred = Credential(provider="google", access_token="a", refresh_token=None)
        assert p.refresh(cred) is None


class TestGitHubOAuth:
    """GitHubOAuth generates correct URLs and parses token responses."""

    def test_name(self):
        p = GitHubOAuth("cid", "csecret")
        assert p.name == "github"

    def test_authorize_url_contains_required_params(self):
        p = GitHubOAuth("gh_client_id", "secret", scopes=["repo", "user"])
        url = p.authorize_url("http://localhost:8080/callback", "state123")

        assert "gh_client_id" in url
        assert "state123" in url
        assert "repo" in url
        assert url.startswith("https://github.com/login/oauth/authorize")

    def test_default_scopes(self):
        p = GitHubOAuth("cid", "csecret")
        url = p.authorize_url("http://localhost:8080/callback", "s")
        assert "repo" in url
        assert "user" in url

    @patch("codeupipe.auth.provider._post_form")
    def test_exchange_code(self, mock_post):
        """exchange_code parses GitHub's token response."""
        mock_post.return_value = {
            "access_token": "gho_abc123",
            "token_type": "bearer",
            "scope": "repo,user",
        }
        p = GitHubOAuth("cid", "csecret")
        cred = p.exchange_code("auth_code", "http://localhost:8080/callback")

        assert cred.provider == "github"
        assert cred.access_token == "gho_abc123"
        assert cred.expiry == 0  # GitHub tokens don't expire
        assert "repo" in cred.scopes

    @patch("codeupipe.auth.provider._post_form")
    def test_exchange_code_error(self, mock_post):
        """GitHub error responses raise RuntimeError."""
        mock_post.return_value = {
            "error": "bad_verification_code",
            "error_description": "The code has expired",
        }
        p = GitHubOAuth("cid", "csecret")
        with pytest.raises(RuntimeError, match="The code has expired"):
            p.exchange_code("bad_code", "http://localhost:8080/callback")

    def test_refresh_no_token(self):
        """Refresh returns None for standard GitHub OAuth (no refresh tokens)."""
        p = GitHubOAuth("cid", "csecret")
        cred = Credential(provider="github", access_token="gho_abc", refresh_token=None)
        assert p.refresh(cred) is None


# ── AuthHook Tests ────────────────────────────────────────────


class TestAuthHook:
    """AuthHook injects credentials into pipeline payload."""

    def test_injects_token_into_payload(self, tmp_path):
        """AuthHook injects access_token before pipeline runs."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        store.save(Credential(
            provider="google",
            access_token="ya29.injected",
            expiry=time.time() + 3600,
        ))

        pipeline = Pipeline()
        pipeline.use_hook(AuthHook(store, provider="google"))
        pipeline.add_filter(EchoFilter(), name="echo")

        result = asyncio.run(pipeline.run(Payload({"input": "test"})))
        assert result.get("echo_token") == "ya29.injected"

    def test_required_raises_when_no_credential(self, tmp_path):
        """required=True raises RuntimeError if no valid credential."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        pipeline = Pipeline()
        pipeline.use_hook(AuthHook(store, provider="missing", required=True))
        pipeline.add_filter(EchoFilter(), name="echo")

        with pytest.raises(RuntimeError, match="No valid credential"):
            asyncio.run(pipeline.run(Payload({})))

    def test_optional_skips_when_no_credential(self, tmp_path):
        """required=False skips injection if no credential found."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        pipeline = Pipeline()
        pipeline.use_hook(AuthHook(store, provider="missing", required=False))
        pipeline.add_filter(EchoFilter(), name="echo")

        result = asyncio.run(pipeline.run(Payload({})))
        assert result.get("echo_token") == "none"

    def test_custom_token_key(self, tmp_path):
        """token_key changes the payload key for the access token."""

        class CheckKey(Filter):
            async def call(self, payload):
                return payload.insert("found", payload.get("google_token", "nope"))

        store = CredentialStore(str(tmp_path / "creds.json"))
        store.save(Credential(
            provider="google",
            access_token="ya29.custom",
            expiry=time.time() + 3600,
        ))

        pipeline = Pipeline()
        pipeline.use_hook(
            AuthHook(store, provider="google", token_key="google_token"),
        )
        pipeline.add_filter(CheckKey(), name="check")

        result = asyncio.run(pipeline.run(Payload({})))
        assert result.get("found") == "ya29.custom"

    def test_only_injects_at_pipeline_start(self, tmp_path):
        """Hook only fires when filter=None (pipeline start), not per-filter."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        store.save(Credential(
            provider="google",
            access_token="ya29.test",
            expiry=time.time() + 3600,
        ))

        hook = AuthHook(store, provider="google")
        payload = Payload({"existing": "data"})

        # Simulate per-filter call (filter is not None) — should be a no-op
        mock_filter = MagicMock()
        asyncio.run(hook.before(mock_filter, payload))
        assert payload.get("access_token") is None

        # Simulate pipeline start (filter=None) — should inject
        asyncio.run(hook.before(None, payload))
        assert payload.get("access_token") == "ya29.test"

    def test_expired_credential_required(self, tmp_path):
        """Required hook raises on expired credential with no refresh possible."""
        store = CredentialStore(str(tmp_path / "creds.json"))
        store.save(Credential(
            provider="google",
            access_token="old",
            expiry=time.time() - 1000,
            refresh_token=None,
        ))

        pipeline = Pipeline()
        pipeline.use_hook(AuthHook(store, provider="google", required=True))
        pipeline.add_filter(EchoFilter(), name="echo")

        with pytest.raises(RuntimeError, match="No valid credential"):
            asyncio.run(pipeline.run(Payload({})))


# ── OAuth Callback Server Tests ───────────────────────────────


class TestOAuthCallbackServer:
    """Local OAuth callback server captures auth codes."""

    def test_successful_callback(self):
        """Server captures auth code from callback."""
        from codeupipe.auth._server import run_oauth_flow

        provider = _FakeProvider()

        def _simulate_callback(url):
            """Parse the auth URL, extract state, hit the callback."""
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            state = params["state"][0]
            redirect = params["redirect_uri"][0]

            # Small delay so server is ready
            time.sleep(0.2)
            callback_url = f"{redirect}?code=test_code_123&state={state}"
            try:
                urllib.request.urlopen(callback_url, timeout=5)
            except Exception:
                pass

        with patch("webbrowser.open") as mock_browser:
            mock_browser.side_effect = lambda url: threading.Thread(
                target=_simulate_callback, args=(url,), daemon=True,
            ).start()

            code, redirect_uri = run_oauth_flow(provider, timeout=10)

        assert code == "test_code_123"
        assert "localhost" in redirect_uri
        assert "/callback" in redirect_uri

    def test_state_mismatch_fails(self):
        """Wrong state parameter causes an error."""
        from codeupipe.auth._server import run_oauth_flow

        provider = _FakeProvider()

        def _simulate_bad_state(url):
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            redirect = params["redirect_uri"][0]

            time.sleep(0.2)
            callback_url = f"{redirect}?code=abc&state=WRONG_STATE"
            try:
                urllib.request.urlopen(callback_url, timeout=5)
            except Exception:
                pass

        with patch("webbrowser.open") as mock_browser:
            mock_browser.side_effect = lambda url: threading.Thread(
                target=_simulate_bad_state, args=(url,), daemon=True,
            ).start()

            with pytest.raises(RuntimeError, match="OAuth flow failed"):
                run_oauth_flow(provider, timeout=10)

    def test_error_from_provider(self):
        """Provider-side error is captured and raised."""
        from codeupipe.auth._server import run_oauth_flow

        provider = _FakeProvider()

        def _simulate_error(url):
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            redirect = params["redirect_uri"][0]

            time.sleep(0.2)
            callback_url = f"{redirect}?error=access_denied&error_description=User+denied"
            try:
                urllib.request.urlopen(callback_url, timeout=5)
            except Exception:
                pass

        with patch("webbrowser.open") as mock_browser:
            mock_browser.side_effect = lambda url: threading.Thread(
                target=_simulate_error, args=(url,), daemon=True,
            ).start()

            with pytest.raises(RuntimeError, match="User denied"):
                run_oauth_flow(provider, timeout=10)

    def test_timeout(self):
        """Flow times out if no callback received."""
        from codeupipe.auth._server import run_oauth_flow

        provider = _FakeProvider()

        with patch("webbrowser.open"):
            with pytest.raises(TimeoutError, match="not received"):
                run_oauth_flow(provider, timeout=1, open_browser=False)

    def test_no_browser_mode(self, capsys):
        """no-browser mode prints URL instead of opening browser."""
        from codeupipe.auth._server import run_oauth_flow

        provider = _FakeProvider()

        def _simulate_callback(url_printed):
            # Wait a moment then hit timeout
            pass

        with patch("webbrowser.open") as mock_browser:
            try:
                run_oauth_flow(provider, timeout=1, open_browser=False)
            except TimeoutError:
                pass
            mock_browser.assert_not_called()

        captured = capsys.readouterr()
        assert "Open this URL" in captured.out


# ── CLI Tests ─────────────────────────────────────────────────


class TestAuthCLI:
    """cup auth subcommands work correctly."""

    def test_auth_status_empty(self, tmp_path, capsys):
        """cup auth status with no stored credentials."""
        from codeupipe.cli import main

        creds_file = str(tmp_path / "creds.json")
        result = main(["auth", "status", "--store", creds_file])
        captured = capsys.readouterr()
        assert "No stored credentials" in captured.out

    def test_auth_status_with_provider(self, tmp_path, capsys):
        """cup auth status shows credential details."""
        from codeupipe.cli import main

        creds_file = str(tmp_path / "creds.json")
        store = CredentialStore(creds_file)
        store.save(Credential(
            provider="google",
            access_token="ya29.test",
            refresh_token="1//ref",
            expiry=time.time() + 3600,
            scopes=["email"],
        ))

        result = main(["auth", "status", "google", "--store", creds_file])
        captured = capsys.readouterr()
        assert "google" in captured.out
        assert "valid" in captured.out

    def test_auth_revoke(self, tmp_path, capsys):
        """cup auth revoke removes credentials."""
        from codeupipe.cli import main

        creds_file = str(tmp_path / "creds.json")
        store = CredentialStore(creds_file)
        store.save(Credential(provider="github", access_token="gho_abc"))

        result = main(["auth", "revoke", "github", "--store", creds_file])
        captured = capsys.readouterr()
        assert "Revoked" in captured.out

        # Verify it's gone
        assert store.get("github") is None

    def test_auth_revoke_nonexistent(self, tmp_path, capsys):
        """cup auth revoke for non-existent provider shows message."""
        from codeupipe.cli import main

        creds_file = str(tmp_path / "creds.json")
        result = main(["auth", "revoke", "nope", "--store", creds_file])
        captured = capsys.readouterr()
        assert "No credentials" in captured.out

    def test_auth_login_missing_client_id(self, capsys):
        """cup auth login without client-id shows error."""
        from codeupipe.cli import main

        # Ensure env vars are not set
        env = {k: v for k, v in os.environ.items()
               if k not in ("CUP_AUTH_CLIENT_ID", "CUP_AUTH_CLIENT_SECRET")}
        with patch.dict(os.environ, env, clear=True):
            result = main(["auth", "login", "google"])
        captured = capsys.readouterr()
        assert result == 1
        assert "client-id" in captured.err.lower() or "client_id" in captured.err.lower()

    def test_auth_login_unknown_provider(self, capsys):
        """cup auth login with unknown provider shows error."""
        from codeupipe.cli import main

        result = main([
            "auth", "login", "myspace",
            "--client-id", "cid",
            "--client-secret", "csecret",
        ])
        captured = capsys.readouterr()
        assert result == 1
        assert "Unknown provider" in captured.err

    def test_auth_help(self, capsys):
        """cup auth without subcommand shows help."""
        from codeupipe.cli import main

        result = main(["auth"])
        captured = capsys.readouterr()
        # argparse prints to stdout
        output = captured.out + captured.err
        assert "login" in output or "status" in output or result == 1
