# codeupipe Auth & Vault — Agent Reference

> `curl https://codeuchain.github.io/codeupipe/agents/auth.txt`

---

## Overview

codeupipe has a built-in OAuth2 system with browser-based login, credential persistence, and a proxy token vault. No external auth libraries needed.

---

## OAuth2 Login

```bash
cup auth login google          # opens browser for Google OAuth2
cup auth login github          # opens browser for GitHub OAuth2
cup auth status google         # check credential state
cup auth revoke google         # remove stored credentials
cup auth list                  # list all providers
```

### Programmatic

```python
from codeupipe.auth import (
    Credential, CredentialStore,
    AuthProvider, GoogleOAuth, GitHubOAuth,
    AuthHook, run_oauth_flow,
)

# Browser-based OAuth2 flow
cred = run_oauth_flow(GoogleOAuth(
    client_id="...",
    client_secret="...",
    scopes=["openid", "email"],
))

# Persistent credential storage
store = CredentialStore("~/.cup/credentials.json")
store.save("google", cred)
cred = store.load("google")  # auto-refreshes if expired

# Pipeline hook — injects credentials before each filter runs
pipeline.use_hook(AuthHook(store, provider="google"))
```

---

## Proxy Token Vault

The vault issues opaque `cup_tok_*` reference tokens instead of exposing real OAuth tokens. Tokens have TTL, scopes, and usage limits.

```bash
cup vault issue google              # issue a proxy token
cup vault resolve cup_tok_xxx       # verify + get real credential
cup vault revoke cup_tok_xxx        # revoke token
cup vault revoke-all                # revoke all active tokens
cup vault list                      # list active tokens
cup vault status cup_tok_xxx        # detailed inspection
```

### Programmatic

```python
from codeupipe.auth import ProxyToken, TokenVault, TokenLedger, VaultHook

vault = TokenVault(credential_store)

# Issue a proxy token (TTL, scopes, usage limits)
token = vault.issue("google", ttl=3600, scopes=["email"], max_uses=10)
# token.value = "cup_tok_a1b2c3d4..."

# Resolve (returns real credential if token is valid)
cred = vault.resolve(token.value)

# Revoke
vault.revoke(token.value)

# Audit trail
ledger = TokenLedger()
vault = TokenVault(credential_store, ledger=ledger)
# ledger.events → list of LedgerEvent (issued, resolved, revoked, expired)

# Pipeline hook — injects proxy tokens instead of real credentials
pipeline.use_hook(VaultHook(vault, provider="google"))
```

---

## Why Proxy Tokens?

- **Principle of least privilege** — filters never see real OAuth tokens
- **Auditability** — every token use is logged in the ledger
- **TTL + usage limits** — tokens auto-expire, can't be reused beyond limits
- **Revocability** — instant revocation without touching OAuth tokens
- **Scope restriction** — proxy tokens can have narrower scopes than the underlying credential
