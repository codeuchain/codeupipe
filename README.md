# codeupipe

<!-- cup:ref file=codeupipe/__init__.py hash=71142af -->

Python pipeline framework — composable **Payload → Filter → Pipeline** pattern with streaming support. Zero external dependencies.

Experimental successor to [codeuchain](https://github.com/codeuchain/codeuchain) (Python only).

<!-- /cup:ref -->

## Core Concepts

<!-- cup:ref file=codeupipe/core/__init__.py hash=af8905e -->
| Concept | Role |
|---|---|
| **Payload** | Immutable data container flowing through the pipeline |
| **MutablePayload** | Mutable sibling for performance-critical bulk edits |
| **Filter** | Processing unit — takes a Payload in, returns a transformed Payload out (sync or async) |
| **StreamFilter** | Streaming processing unit — receives one chunk, yields 0, 1, or N output chunks |
| **Pipeline** | Orchestrator — `.run()` for batch, `.stream()` for streaming |
| **Valve** | Conditional flow control — gates a Filter with a predicate |
| **Tap** | Non-modifying observation point — inspect without changing (sync or async) |
| **State** | Pipeline execution metadata — tracks what ran, what was skipped, errors, chunk counts |
| **Hook** | Lifecycle hooks — before/after/on_error for pipeline execution (sync or async) |
| **RetryFilter** | Resilience wrapper — retries a Filter up to N times before giving up |
| **CircuitOpenError** | Raised when a pipeline circuit breaker is open and rejecting calls |
<!-- /cup:ref -->

## CUP Products — The Device Mesh

codeupipe isn't just a framework — it's the architecture underneath a mesh of connected devices. Every product below is built from the same Payload → Filter → Pipeline primitives.

```
┌─────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  Mobile  │────▶│ Platform SPA │────▶│  Extension   │────▶│ Desktop  │
│  Device  │◀────│ (Static Page)│◀────│ (MV3 Bridge) │◀────│ Compute  │
└─────────┘     └──────────────┘     └──────────────┘     └──────────┘
      │                                      │                    │
      │           CUP Pipelines              │                    │
      │         at every hop ───────────────▶│                    │
      │                                      ▼                    ▼
      │                               ┌──────────┐        ┌──────────┐
      └──────────────────────────────▶│  Native  │───────▶│ Servers  │
                                      │   Host   │        │ DB / GPU │
                                      └──────────┘        └──────────┘
```

A phone triggers a static web page. The page talks to a browser extension. The extension relays to a native host running on the physical machine — with full access to databases, GPU compute, local files, and anything else on the box. Every hop is a CUP pipeline. The same mesh works in reverse.

| Product | What It Does | Status |
|---------|-------------|--------|
| **CUP Core** | Payload → Filter → Pipeline framework (Python, TS, Rust, Go) | ✅ Live |
| **CUP Bridge** | Generic browser bridge — 3 tiers (Native Messaging, HTTP, WASM) | ✅ Live |
| **CUP Browser** | 10 browser automation filters + PlaywrightBridge SDK | ✅ Live |
| **CUP Extension** | MV3 browser extension — Chrome, Edge, Brave, Arc | ✅ Live |
| **CUP Platform** | GitHub Pages SPA — dashboard, capability store, recipe install | ✅ [Live](https://codeuchain.github.io/codeupipe/platform/) |
| **CUP AI** | Agent SDK, providers, discovery, TUI, eval | ✅ Live |
| **CUP Marketplace** | Community connector index — `cup marketplace search` | ✅ Live |
| **CUP Mobile** | AdbBridge (Android) + IosBridge (iOS) device automation | 🔜 Planned |

> **Why this matters:** Because codeupipe is modular, every product is a set of filters. Combine them freely — a single pipeline can read a phone sensor, process it in WASM, store it in Postgres, and push a notification back to the device. The architecture is the product.

## Install

```bash
pip install -e .
```

## Quick Start

```python
import asyncio
from codeupipe import Payload, Pipeline

# Filters can be sync or async — both work
class CleanInput:
    def call(self, payload):
        return payload.insert("text", payload.get("text", "").strip())

class Validate:
    def call(self, payload):
        if not payload.get("text"):
            raise ValueError("Empty input")
        return payload

# Build and run
pipeline = Pipeline()
pipeline.add_filter(CleanInput(), name="clean")
pipeline.add_filter(Validate(), name="validate")

result = asyncio.run(pipeline.run(Payload({"text": "  hello  "})))
print(result.get("text"))  # "hello"
```

## Valve (Conditional Flow)

```python
from codeupipe import Valve

class DiscountFilter:
    def call(self, payload):
        price = payload.get("price", 0)
        return payload.insert("price", price * 0.9)

# Only applies when predicate returns True
pipeline.add_filter(
    Valve("discount", DiscountFilter(), lambda p: p.get("tier") == "premium"),
    name="discount",
)
```

## Tap (Observation)

```python
class AuditTap:
    async def observe(self, payload):
        print(f"Payload at this point: {payload.to_dict()}")

pipeline.add_tap(AuditTap(), name="audit")
```

## Streaming

Process an async stream of chunks through the same pipeline at constant memory.

```python
from codeupipe import Payload, Pipeline

class UppercaseFilter:
    def call(self, payload):
        return payload.insert("name", payload.get("name", "").upper())

async def names():
    for n in ["alice", "bob", "charlie"]:
        yield Payload({"name": n})

async def main():
    pipeline = Pipeline()
    pipeline.add_filter(UppercaseFilter(), name="upper")

    async for result in pipeline.stream(names()):
        print(result.get("name"))  # ALICE, BOB, CHARLIE

asyncio.run(main())
```

Use `StreamFilter` to drop, fan-out, or batch:

```python
from typing import AsyncIterator

class DropEmpty:
    async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
        if chunk.get("line", "").strip():
            yield chunk

class SplitWords:
    async def stream(self, chunk: Payload) -> AsyncIterator[Payload]:
        for word in chunk.get("text", "").split():
            yield Payload({"word": word})
```

## Synchronous Execution

No manual `asyncio.run()` needed — `run_sync()` handles it:

```python
pipeline = Pipeline()
pipeline.add_filter(CleanInput(), name="clean")
pipeline.add_filter(Validate(), name="validate")

result = pipeline.run_sync(Payload({"text": "  hello  "}))
print(result.get("text"))  # "hello"
```

## Parallel Execution (Fan-out / Fan-in)

Run independent filters concurrently; results merge back into the payload:

```python
pipeline = Pipeline()
pipeline.add_parallel([
    FetchUserFilter(),
    FetchOrdersFilter(),
    FetchRecommendationsFilter(),
], name="fan-out")

result = pipeline.run_sync(Payload({"user_id": 42}))
```

## Pipeline Nesting

Compose pipelines from smaller pipelines:

```python
validation = Pipeline()
validation.add_filter(CleanInput(), name="clean")
validation.add_filter(Validate(), name="validate")

processing = Pipeline()
processing.add_pipeline(validation, name="validation-sub")
processing.add_filter(TransformFilter(), name="transform")

result = processing.run_sync(Payload({"text": "  hello  "}))
```

## Retry & Circuit Breaker

Pipeline-level resilience wrappers:

```python
# Retry the entire pipeline up to 3 times on failure
retrying = pipeline.with_retry(max_retries=3)
result = retrying.run_sync(Payload({"input": "data"}))

# Open the circuit after 5 consecutive failures
from codeupipe import CircuitOpenError

breaker = pipeline.with_circuit_breaker(failure_threshold=5)
try:
    result = breaker.run_sync(Payload({"input": "data"}))
except CircuitOpenError:
    print("Service unavailable — circuit is open")
```

## Execution State

```python
result = await pipeline.run(payload)
print(pipeline.state.executed)           # ['clean', 'validate']
print(pipeline.state.skipped)            # ['admin_only']
print(pipeline.state.chunks_processed)   # {'upper': 3}  (streaming mode)
```

## Docs

| Document | Purpose |
|----------|---------|
| [INDEX.md](INDEX.md) | Project structure map (verified by `cup doc-check`) |
| [CONCEPTS.md](CONCEPTS.md) | Full API reference with runnable examples |
| [BEST_PRACTICES.md](BEST_PRACTICES.md) | Project structure, naming, testing strategy |
| [SKILL.md](SKILL.md) | Agent skill reference — types, patterns, conversion |
| [ROADMAP.md](ROADMAP.md) | Expansion rings — from framework to platform |

## CLI (`cup`)

<!-- cup:ref file=codeupipe/cli/__init__.py symbols=main hash=b8fbe58 -->
<!-- cup:ref file=codeupipe/cli/_registry.py symbols=CommandRegistry hash=8e82ece -->
<!-- cup:ref file=codeupipe/cli/_scaffold.py symbols=scaffold,COMPONENT_TYPES hash=1f62e60 -->
<!-- cup:ref file=codeupipe/cli/_bundle.py symbols=bundle hash=9a1b776 -->
<!-- cup:ref file=codeupipe/cli/commands/analysis_cmds.py symbols=lint,coverage,report,doc_check hash=f2e1df8 -->
The `cup` command-line tool scaffolds, lints, and analyzes CUP projects:

```bash
cup new filter validate_email src/signup   # Scaffold a filter + test
cup new pipeline signup src/signup --steps validate_email hash_password
cup list                                   # Show available component types
cup bundle src/signup                      # Generate __init__.py re-exports
cup lint src/signup                        # Check CUP conventions (CUP000–CUP008)
cup coverage src/signup                    # Map component↔test coverage gaps
cup report src/signup                      # Health report with scores, orphans, staleness
cup doc-check .                            # Verify doc freshness (cup:ref markers)
cup run pipeline.json --discover ./filters # Execute a pipeline from config
cup connect --list                         # Show configured connectors
cup connect --health                       # Run connector health checks
cup marketplace search "payments"          # Search community connectors
cup marketplace info codeupipe-stripe      # Detailed connector info
cup marketplace install codeupipe-stripe   # Install from PyPI
cup describe pipeline.json                 # Inspect pipeline inputs, outputs, steps
cup describe pipeline.json --json          # Machine-readable output (--json works globally)
cup distribute checkpoint cp.json --status # Manage payload checkpoints
cup distribute remote https://api.example  # Test a remote filter endpoint
cup test                                   # Smart test runner with markers
cup doctor                                 # Project health diagnostics
cup graph pipeline.json                    # Mermaid pipeline visualization
cup version --bump patch                   # Show/bump semver
```
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->

## Marketplace & Community Connectors

The [**codeupipe Marketplace**](https://github.com/codeuchain/codeupipe-marketplace) is a community-driven index of connectors and components. Packages live on PyPI — the marketplace makes them discoverable.

```bash
# Find connectors
cup marketplace search "ai"
# → codeupipe-google-ai ✅ (v0.1.0) — Multimodal generation, embeddings, and vision

# Install (wrapper around pip install)
cup marketplace install codeupipe-google-ai

# Connector self-registers — immediately available
cup connect --list
# → google-ai: GeminiGenerate, GeminiGenerateStream, GeminiEmbed, GeminiVision
```

### Available Connectors

| Package | Provider | Filters |
|---------|----------|---------|
| `codeupipe-google-ai` | Google AI (Gemini) | GeminiGenerate, GeminiGenerateStream, GeminiEmbed, GeminiVision |
| `codeupipe-stripe` | Stripe | StripeCheckout, StripeSubscription, StripeWebhook, StripeCustomer |
| `codeupipe-postgres` | PostgreSQL | PostgresQuery, PostgresExecute, PostgresTransaction, PostgresBulkInsert |
| `codeupipe-resend` | Resend | ResendEmail, ResendTemplate |

### Publish Your Own

Built a connector? Share it with the community:

1. Publish your package to PyPI with `codeupipe.connectors` entry points
2. Fork [codeuchain/codeupipe-marketplace](https://github.com/codeuchain/codeupipe-marketplace)
3. Add a `manifest.json` for your package
4. Open a PR — CI validates automatically

See the [Marketplace Contributing Guide](https://github.com/codeuchain/codeupipe-marketplace/blob/main/CONTRIBUTING.md) for the full walkthrough.

## Auth & Vault

<!-- cup:ref file=codeupipe/auth/__init__.py hash=85c76a2 -->
<!-- cup:ref file=codeupipe/auth/proxy_token.py symbols=ProxyToken hash=686c997 -->
<!-- cup:ref file=codeupipe/auth/token_vault.py symbols=TokenVault hash=dfd347f -->
<!-- cup:ref file=codeupipe/auth/vault_hook.py symbols=VaultHook hash=899f08a -->
<!-- cup:ref file=codeupipe/cli/commands/vault_cmds.py symbols=setup hash=d2fb81a -->

codeupipe ships a **proxy token vault** that decouples pipelines from real
credentials.  Instead of passing raw access tokens through Payload, the vault
issues opaque `cup_tok_*` references.  Filters only ever see the proxy —
resolution to the real credential happens at the trust boundary via `VaultHook`.

```
┌──────────┐      cup_tok_abc123      ┌───────────┐
│ Pipeline │ ───────────────────────► │ VaultHook │
│ (filters │                          │  resolve   │
│  see tok)│ ◄─────────────────────── │  ↕ Vault   │
└──────────┘    real access_token     └───────────┘
```

### Quick usage

```python
from codeupipe.auth import (
    TokenVault, VaultHook, CredentialStore, GoogleOAuth,
)

store = CredentialStore("tokens.json")
vault = TokenVault(store)

# Inject proxy tokens automatically
pipeline.use_hook(VaultHook(vault, GoogleOAuth(...), scope="calendar"))
result = await pipeline.run(Payload({"user": "alice"}))
# Filters receive payload["credential"] as a cup_tok_* proxy
```

### Vault CLI

```bash
cup vault issue google calendar          # Issue a scoped proxy token
cup vault resolve cup_tok_abc123         # Resolve to real credential (admin only)
cup vault revoke cup_tok_abc123          # Revoke a single token
cup vault revoke-all                     # Revoke every active token
cup vault list                           # Show active proxy tokens
cup vault status                         # Vault summary + ledger stats
```

Every vault action is recorded in the **TokenLedger** audit trail.
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->

## Testing Utilities

<!-- cup:ref file=codeupipe/testing.py symbols=run_filter,assert_payload,mock_filter hash=65f0296 -->
`codeupipe.testing` provides zero-boilerplate test helpers:

```python
from codeupipe.testing import run_filter, assert_payload, mock_filter

def test_my_filter():
    result = run_filter(MyFilter(), {"input": "data"})
    assert_payload(result, output="expected")

def test_with_mock():
    f = mock_filter(status="ok")
    result = run_filter(f, {"x": 1})
    assert f.call_count == 1
```
<!-- /cup:ref -->

## Test

```bash
pytest  # 1844 tests
```

## License

Apache 2.0
