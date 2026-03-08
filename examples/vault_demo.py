"""
Vault Demo: Proxy Token Indirection (the OTP pattern)

Shows how the CUP vault issues short-lived, single-use proxy tokens
instead of passing real OAuth credentials through a pipeline.

Think of it like Google Authenticator:
  • Real credential = your password (long-lived, high-value)
  • Proxy token     = OTP code     (ephemeral, narrow scope, auto-expires)

Filters only ever see the OTP-like proxy.  Resolution to the real
credential happens at the trust boundary — right before the actual API call.

No real Google account needed — this demo uses a mock credential store.

Usage:
    python examples/vault_demo.py
"""

import asyncio
import sys
import os
import time
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from codeupipe import Payload, Filter, Pipeline, Tap, Hook
from codeupipe.auth import (
    Credential,
    CredentialStore,
    ProxyToken,
    TokenLedger,
    TokenVault,
    VaultHook,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def seed_mock_credential(store: CredentialStore) -> None:
    """Plant a fake Google credential so the vault has something to issue against."""
    cred = Credential(
        provider="google",
        access_token="ya29.REAL_SECRET_TOKEN_DO_NOT_LEAK",
        refresh_token="1//REAL_REFRESH_TOKEN",
        token_type="Bearer",
        expiry=time.time() + 3600,  # 1 hour from now
        scopes=["calendar", "email"],
    )
    store.save(cred)


# ── Filters ────────────────────────────────────────────────────────────────

class ShowCredential(Filter):
    """Demonstrates that the filter ONLY sees the proxy token, not the real one."""

    async def call(self, payload: Payload) -> Payload:
        token = payload.get("access_token") or ""
        provider = payload.get("auth_provider") or ""

        print(f"\n  🔑 Filter sees credential:")
        print(f"     provider    : {provider}")
        print(f"     access_token: {token[:30]}...")
        print(f"     starts with 'cup_tok_': {token.startswith('cup_tok_')}")
        print(f"     is real token: {token.startswith('ya29.')}")
        return payload.insert("filter_saw_proxy", token.startswith("cup_tok_"))


class SimulateAPICall(Filter):
    """Pretends to call an external API using the proxy token.

    In a real app, a trust-boundary adapter would resolve the proxy
    to the real credential right before the HTTP call goes out.
    """

    async def call(self, payload: Payload) -> Payload:
        token = payload.get("access_token") or ""
        print(f"\n  🌐 Simulating API call with token: {token[:30]}...")
        # In production: real_cred = vault.resolve(token)
        # Then use real_cred.access_token in the HTTP header
        return payload.insert("api_result", {"events": 42, "source": "mock"})


class ShowResult(Filter):
    """Print the final result."""

    async def call(self, payload: Payload) -> Payload:
        result = payload.get("api_result") or {}
        print(f"\n  ✅ API returned: {result}")
        return payload


# ── Taps ───────────────────────────────────────────────────────────────────

class AuditTap(Tap):
    """Observe the payload at each stage — notice the real token never appears."""

    def __init__(self):
        self.snapshots = []

    async def observe(self, payload: Payload) -> None:
        self.snapshots.append(payload.to_dict().copy())


# ── Demo 1: VaultHook in a Pipeline ───────────────────────────────────────

async def demo_vault_pipeline(store_path: str) -> None:
    """Full pipeline with VaultHook — automatic proxy token lifecycle."""

    print("═" * 60)
    print("  Demo 1: VaultHook Pipeline (automatic OTP-like tokens)")
    print("═" * 60)

    store = CredentialStore(store_path)
    seed_mock_credential(store)

    vault = TokenVault(store)
    audit = AuditTap()

    pipeline = Pipeline()
    pipeline.use_hook(VaultHook(
        vault,
        provider="google",
        ttl=60,               # Token lives for 60 seconds max
        scope_level="run",    # Scoped to this pipeline run
        max_uses=2,           # Can be resolved at most 2 times
        scopes=["calendar"],
    ))
    pipeline.add_filter(ShowCredential(), "show_credential")
    pipeline.add_tap(audit, "after_show")
    pipeline.add_filter(SimulateAPICall(), "api_call")
    pipeline.add_tap(audit, "after_api")
    pipeline.add_filter(ShowResult(), "show_result")

    print("\n  ▶ Running pipeline...")
    result = await pipeline.run(Payload({"user": "alice"}))

    # After pipeline: vault has auto-revoked
    print(f"\n  🔒 Active tokens after pipeline: {vault.active_count()}")
    print(f"  📋 Ledger events: {len(vault.ledger.events())}")
    for event in vault.ledger.events():
        print(f"     {event.event:10s} | {event.token[:25]}... | {event.provider}")

    # Verify the real token never appeared in any tap snapshot
    real_token_leaked = any(
        "ya29." in str(snap.get("access_token", ""))
        for snap in audit.snapshots
    )
    print(f"\n  🛡️  Real token leaked to filters: {real_token_leaked}")
    assert not real_token_leaked, "Real token should NEVER appear in payload!"
    assert result.get("filter_saw_proxy") is True


# ── Demo 2: Manual Vault Operations ──────────────────────────────────────

async def demo_manual_vault(store_path: str) -> None:
    """Manual proxy token lifecycle — like managing OTP codes yourself."""

    print("\n\n" + "═" * 60)
    print("  Demo 2: Manual Vault Operations (the OTP analogy)")
    print("═" * 60)

    store = CredentialStore(store_path)
    seed_mock_credential(store)

    ledger = TokenLedger()
    vault = TokenVault(store, ledger)

    # Issue — like generating an OTP
    print("\n  1️⃣  Issuing proxy token (= generating an OTP)...")
    proxy = vault.issue(
        provider="google",
        scopes=["calendar"],
        ttl=30,              # 30 second lifetime
        scope_level="single-use",
        max_uses=1,          # One-time use, just like a real OTP
    )
    print(f"     Token  : {proxy.token[:30]}...")
    print(f"     TTL    : {proxy.ttl}s")
    print(f"     Max use: {proxy.max_uses}")
    print(f"     Valid  : {proxy.valid}")

    # Resolve — like entering the OTP to get access
    print("\n  2️⃣  Resolving proxy → real credential (= entering the OTP)...")
    real_cred = vault.resolve(proxy.token)
    print(f"     Real token: {real_cred.access_token[:12]}...{real_cred.access_token[-4:]}")
    print(f"     Provider  : {real_cred.provider}")

    # Exhausted — the OTP is now used up
    print("\n  3️⃣  Checking exhaustion (= OTP already used)...")
    print(f"     Exhausted: {proxy.exhausted}")
    print(f"     Usage    : {proxy.usage_count}/{proxy.max_uses}")
    try:
        vault.resolve(proxy.token)
        print("     ⚠️  Should not reach here!")
    except RuntimeError as e:
        print(f"     ✅ Blocked: {e}")

    # Revoke — invalidate early (like revoking a session)
    print("\n  4️⃣  Revoking the token (= invalidating early)...")
    vault.revoke(proxy.token)
    print(f"     Revoked: {proxy.revoked}")
    print(f"     Valid  : {proxy.valid}")

    # Audit trail
    print("\n  📋 Full audit trail:")
    for event in ledger.events():
        ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
        print(f"     [{ts}] {event.event:10s} | {event.token[:25]}... | {event.provider}")


# ── Demo 3: Emergency Revoke-All ─────────────────────────────────────────

async def demo_emergency_revoke(store_path: str) -> None:
    """Simulate an emergency: revoke all active tokens at once."""

    print("\n\n" + "═" * 60)
    print("  Demo 3: Emergency Revoke-All")
    print("═" * 60)

    store = CredentialStore(store_path)
    seed_mock_credential(store)

    vault = TokenVault(store)

    # Issue several tokens
    tokens = []
    for i in range(5):
        proxy = vault.issue(provider="google", scopes=["calendar"], ttl=300)
        tokens.append(proxy)
    print(f"\n  Issued {len(tokens)} proxy tokens")
    print(f"  Active: {vault.active_count()}")

    # Emergency revoke
    print("\n  🚨 Emergency! Revoking all tokens...")
    revoked = vault.revoke_all()
    print(f"  Revoked: {revoked}")
    print(f"  Active:  {vault.active_count()}")

    # Verify none can be resolved
    for tok in tokens:
        assert not tok.valid, f"Token {tok.token[:20]} should be revoked!"
    print("  ✅ All tokens invalid — credentials are safe")


# ── Main ───────────────────────────────────────────────────────────────────

async def main():
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║  codeupipe Vault Demo — Proxy Token Indirection     ║")
    print("  ║  (Think Google Authenticator, but for pipelines)    ║")
    print("  ╚══════════════════════════════════════════════════════╝")

    # Use a temp directory so the demo is self-contained
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "credentials.json")

        await demo_vault_pipeline(store_path)
        await demo_manual_vault(store_path)
        await demo_emergency_revoke(store_path)

    print("\n\n  Done! No real credentials were harmed in this demo. 🎉\n")


if __name__ == "__main__":
    asyncio.run(main())
