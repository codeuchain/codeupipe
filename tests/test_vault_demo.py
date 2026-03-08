"""
Tests for examples/vault_demo.py — verify each demo scenario runs cleanly.

Run with:  pytest tests/test_vault_demo.py -v
"""

import asyncio
import os
import tempfile
import time

import pytest

from codeupipe import Payload, Pipeline, Filter, Tap
from codeupipe.auth import (
    Credential,
    CredentialStore,
    ProxyToken,
    TokenLedger,
    TokenVault,
    VaultHook,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_store(path: str) -> CredentialStore:
    """Create a store with a mock Google credential."""
    store = CredentialStore(path)
    cred = Credential(
        provider="google",
        access_token="ya29.REAL_SECRET_TOKEN_DO_NOT_LEAK",
        refresh_token="1//REAL_REFRESH",
        token_type="Bearer",
        expiry=time.time() + 3600,
        scopes=["calendar", "email"],
    )
    store.save(cred)
    return store


# ---------------------------------------------------------------------------
# Demo 1: VaultHook Pipeline
# ---------------------------------------------------------------------------

class TestVaultHookPipeline:
    """Mirrors Demo 1 from vault_demo.py."""

    def test_filter_only_sees_proxy_token(self):
        """Filters receive cup_tok_*, never the real ya29.* token."""
        seen_tokens = []

        class Capture(Filter):
            async def call(self, payload: Payload) -> Payload:
                seen_tokens.append(payload.get("access_token") or "")
                return payload

        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)

            pipeline = Pipeline()
            pipeline.use_hook(VaultHook(
                vault, provider="google",
                ttl=60, scope_level="run", max_uses=2, scopes=["calendar"],
            ))
            pipeline.add_filter(Capture(), "capture")

            result = asyncio.run(pipeline.run(Payload({"user": "alice"})))

        assert len(seen_tokens) == 1
        assert seen_tokens[0].startswith("cup_tok_")
        assert not seen_tokens[0].startswith("ya29.")

    def test_auto_revoke_after_pipeline(self):
        """VaultHook auto-revokes all tokens when pipeline completes."""

        class NoOp(Filter):
            async def call(self, payload: Payload) -> Payload:
                return payload

        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)

            pipeline = Pipeline()
            pipeline.use_hook(VaultHook(
                vault, provider="google",
                ttl=60, scope_level="run",
            ))
            pipeline.add_filter(NoOp(), "noop")

            asyncio.run(pipeline.run(Payload({})))

        assert vault.active_count() == 0

    def test_auto_revoke_on_error(self):
        """VaultHook auto-revokes even when a filter raises."""

        class Boom(Filter):
            async def call(self, payload: Payload) -> Payload:
                raise RuntimeError("filter exploded")

        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)

            pipeline = Pipeline()
            pipeline.use_hook(VaultHook(
                vault, provider="google",
                ttl=60, scope_level="run",
            ))
            pipeline.add_filter(Boom(), "boom")

            with pytest.raises(RuntimeError, match="filter exploded"):
                asyncio.run(pipeline.run(Payload({})))

        assert vault.active_count() == 0

    def test_real_token_never_in_tap_snapshot(self):
        """Taps observe payloads — the real credential must never appear."""

        class SnapshotTap(Tap):
            def __init__(self):
                self.snaps = []

            async def observe(self, payload: Payload) -> None:
                self.snaps.append(payload.to_dict().copy())

        class Identity(Filter):
            async def call(self, payload: Payload) -> Payload:
                return payload

        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)
            tap = SnapshotTap()

            pipeline = Pipeline()
            pipeline.use_hook(VaultHook(
                vault, provider="google",
                ttl=60, scope_level="run",
            ))
            pipeline.add_filter(Identity(), "identity")
            pipeline.add_tap(tap, "snapshot")

            asyncio.run(pipeline.run(Payload({"user": "bob"})))

        for snap in tap.snaps:
            token_val = str(snap.get("access_token", ""))
            assert not token_val.startswith("ya29."), "Real token leaked to tap!"
            assert token_val.startswith("cup_tok_")

    def test_ledger_records_issue_and_revoke(self):
        """After a pipeline run, the ledger has at least issued + revoked."""

        class Identity(Filter):
            async def call(self, payload: Payload) -> Payload:
                return payload

        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)

            pipeline = Pipeline()
            pipeline.use_hook(VaultHook(
                vault, provider="google",
                ttl=60, scope_level="run",
            ))
            pipeline.add_filter(Identity(), "identity")

            asyncio.run(pipeline.run(Payload({})))

        events = vault.ledger.events()
        event_types = [e.event for e in events]
        assert "issued" in event_types
        assert "revoked" in event_types


# ---------------------------------------------------------------------------
# Demo 2: Manual Vault Operations (OTP analogy)
# ---------------------------------------------------------------------------

class TestManualVaultOTP:
    """Mirrors Demo 2 from vault_demo.py."""

    def test_issue_creates_valid_proxy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)

            proxy = vault.issue(
                provider="google", scopes=["calendar"],
                ttl=30, scope_level="single-use", max_uses=1,
            )

        assert proxy.token.startswith("cup_tok_")
        assert proxy.valid
        assert proxy.ttl == 30
        assert proxy.max_uses == 1

    def test_resolve_returns_real_credential(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)

            proxy = vault.issue(
                provider="google", scopes=["calendar"],
                ttl=30, scope_level="run",
            )
            cred = vault.resolve(proxy.token)

        assert cred.access_token == "ya29.REAL_SECRET_TOKEN_DO_NOT_LEAK"
        assert cred.provider == "google"

    def test_single_use_blocks_second_resolve(self):
        """Like entering an OTP twice — second attempt is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)

            proxy = vault.issue(
                provider="google", scopes=["calendar"],
                ttl=30, scope_level="single-use", max_uses=1,
            )
            vault.resolve(proxy.token)  # First use — OK

            assert proxy.exhausted
            with pytest.raises(RuntimeError, match="exhausted"):
                vault.resolve(proxy.token)  # Second use — blocked

    def test_revoked_token_cannot_resolve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)

            proxy = vault.issue(
                provider="google", scopes=["calendar"], ttl=300,
            )
            vault.revoke(proxy.token)

            assert proxy.revoked
            assert not proxy.valid
            with pytest.raises(RuntimeError, match="revoked"):
                vault.resolve(proxy.token)

    def test_full_audit_trail(self):
        """Issue → resolve → revoke produces three ledger events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            ledger = TokenLedger()
            vault = TokenVault(store, ledger)

            proxy = vault.issue(
                provider="google", scopes=["calendar"],
                ttl=30, scope_level="single-use", max_uses=1,
            )
            vault.resolve(proxy.token)
            vault.revoke(proxy.token)

        events = ledger.events()
        assert len(events) == 3
        assert events[0].event == "issued"
        assert events[1].event == "resolved"
        assert events[2].event == "revoked"
        # All events reference the same token
        assert all(e.token == proxy.token for e in events)


# ---------------------------------------------------------------------------
# Demo 3: Emergency Revoke-All
# ---------------------------------------------------------------------------

class TestEmergencyRevoke:
    """Mirrors Demo 3 from vault_demo.py."""

    def test_revoke_all_invalidates_all_tokens(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)

            tokens = [
                vault.issue(provider="google", scopes=["calendar"], ttl=300)
                for _ in range(5)
            ]
            assert vault.active_count() == 5

            revoked = vault.revoke_all()

            assert revoked == 5
            assert vault.active_count() == 0
            assert all(not t.valid for t in tokens)

    def test_revoke_all_by_provider(self):
        """Only revokes tokens for the specified provider."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            # Also seed a github credential
            store.save(Credential(
                provider="github",
                access_token="gho_FAKE_GITHUB_TOKEN",
                expiry=time.time() + 3600,
                scopes=["repo"],
            ))
            vault = TokenVault(store)

            google_tok = vault.issue(provider="google", scopes=["calendar"], ttl=300)
            github_tok = vault.issue(provider="github", scopes=["repo"], ttl=300)

            revoked = vault.revoke_all(provider="google")

            assert revoked == 1
            assert not google_tok.valid
            assert github_tok.valid  # Untouched

    def test_revoked_tokens_cannot_be_resolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _seed_store(os.path.join(tmpdir, "creds.json"))
            vault = TokenVault(store)

            tokens = [
                vault.issue(provider="google", scopes=["calendar"], ttl=300)
                for _ in range(3)
            ]
            vault.revoke_all()

            for tok in tokens:
                with pytest.raises(RuntimeError, match="revoked"):
                    vault.resolve(tok.token)
