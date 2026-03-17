# codeupipe Roadmap

The expansion plan for codeupipe — from pipeline framework to full-stack production accelerator.

The guiding principle: **zero to production in moments.** Every ring we add should shrink the distance between an idea and a running, monitored, monetizable system.

---

## Where We Are

```
Ring 1  Ship           ████████████  v0.1.0  ✅
Ring 2  Compose        ████████████  v0.2.0  ✅
Ring 3  Execute        ████████████  v0.3.0  ✅
Ring 4  Observe        ████████████  v0.4.0  ✅
Ring 5  Distribute     ████████████  v0.4.0  ✅
Ring 6  Govern         ████████████  v0.5.0  ✅  (no tag — bundled into v0.4.0 release)
Ring 7  Accelerate     ████████████  v0.7.0  ✅
Ring 8  Connect        ████████████  v0.8.0  ✅
Ring 9  Marketplace    ████████████  v0.9.0  ✅
Ring 10 Secure Config  ████████████  v0.10.0 ✅
Ring 11 Polyglot Core  ████████████  v0.11.0 ✅
Ring 12 AI Suite       ████████████  v0.12.0 ✅  ← YOU ARE HERE
```

**3351 total tests: 2130 core Python + 1221 AI suite Python + 88 TypeScript + 59 Rust + 68 Go = 3566 across all languages. 236 doc refs verified. Zero external dependencies in core.**

---

## Completed Rings

### Ring 1 — Ship ✅ (v0.1.0)

Automated release pipeline. Push to main, tag, publish to PyPI.

- CI workflow (Python 3.9–3.13 matrix, pytest, lint)
- Release workflow (tag `v*` → build → publish to PyPI)
- `cup` CLI with 9 commands (scaffold, lint, bundle, coverage, report, doc-check, run)
- `cup:ref` doc verification system + pre-commit hook enforcement

### Ring 2 — Compose ✅ (v0.2.0)

Name-based component catalog and config-driven pipeline assembly.

- `Registry` — register, get, discover, `cup_component` decorator
- `Pipeline.from_config()` — build pipelines from TOML/JSON configs
- `cup run` — execute config-driven pipelines from CLI
- AST-based auto-discovery of filter/tap/hook/stream-filter components

### Ring 3 — Execute ✅ (v0.3.0)

Execution modes, parallelism, nesting, and resilience.

- `run_sync()` — synchronous convenience (no manual `asyncio.run()`)
- `add_parallel()` — fan-out/fan-in with `asyncio.gather`
- `add_pipeline()` — nest pipelines as steps, arbitrary depth
- `with_retry()` / `with_circuit_breaker()` — pipeline-level resilience
- Full config support for parallel, nesting, retry, and circuit breaker

### Ring 4 — Observe ✅ (v0.4.0)

Know what your pipeline is doing without instrumenting every filter by hand.

- **Timing middleware** — automatic per-step duration tracking in `State.timings`
- **Payload lineage** — trace ID and step lineage propagate through Payload operations
- **Structured event emitter** — `PipelineEvent` / `EventEmitter` with `pipeline.on()` / `pipeline.off()`
- Events: `pipeline.start`, `pipeline.end`, `step.start`, `step.end`, `step.error`, `pipeline.retry`, `circuit.open`
- **`pipeline.describe()`** — machine-readable tree of pipeline structure
- **State diffing** — `state.diff(other)` compares two pipeline runs
- Config-driven: `"pipeline": { "observe": { "timing": true, "lineage": true } }`

### Ring 5 — Distribute ✅ (v0.4.0)

Cross-process and network boundaries without changing pipeline logic.

- **Payload serialization** — `payload.serialize()` / `Payload.deserialize()` (JSON)
- **RemoteFilter** — HTTP-based filter that sends payloads to remote services (stdlib urllib)
- **Checkpoint + CheckpointHook** — persist payload state for crash recovery
- **Source adapters** — `IterableSource`, `FileSource` for `pipeline.stream()`
- **WorkerPool** — thread/process pool for CPU-bound work inside filters

### Ring 6 — Govern ✅ (v0.5.0)

Guarantees at the pipeline level — shape, time, rate, and failure policy.

- **PayloadSchema** — shape validation with key presence + type checking, `PayloadSchema.keys()` shorthand
- **Pipeline contracts** — `pipeline.require_input()` / `pipeline.guarantee_output()` for pre/post conditions
- **Schema validation** — `pipeline.require_input_schema()` / `pipeline.guarantee_output_schema()` on run boundaries
- **Timeout policies** — `pipeline.with_timeout(seconds=5)` with clean cancellation via `PipelineTimeoutError`
- **Rate limiting** — `pipeline.with_rate_limit(calls_per_second=10)` token-bucket throttle
- **Dead letter handling** — `pipeline.with_dead_letter(handler)` routes failures to `DeadLetterHandler`
- **Audit trail** — `AuditTrail` + `AuditHook` for immutable transformation logging, `pipeline.enable_audit()`
- **LogDeadLetterHandler** — built-in dead letter collector for testing and debugging
- Events: `pipeline.timeout`, `dead_letter`
- Config-driven: `timeout`, `rate_limit`, `require_input`, `guarantee_output`, `dead_letter`

### Ring 7 — Accelerate ✅ (v0.7.0)

Zero to production. Intent → scaffold → deploy.

- `codeupipe.deploy` package — `DeployAdapter` protocol, `DeployTarget` metadata, adapter discovery via entry points
- `DockerAdapter` — Dockerfile, entrypoint, requirements.txt (auto-detects http/worker/cli mode)
- `VercelAdapter` / `NetlifyAdapter` — serverless handler wrappers + frontend scaffolding
- `cup.toml` manifest parser — project metadata, deploy target, dependencies
- Recipe engine — `resolve_recipe()` with `${variable}` substitution, 5 bundled templates (saas-signup, api-crud, etl, ai-chat, webhook-handler)
- `cup init` project scaffolding — 4 templates (saas, api, etl, chatbot), generates cup.toml, pyproject.toml, pipelines/, filters/, tests/, CI workflow, README
- CLI: `cup deploy`, `cup recipe`, `cup init`

### Ring 8 — Connect ✅ (v0.8.0)

Connector protocol — standardized way to wire external services into pipelines.

- `ConnectorConfig` — parse `[connectors.*]` from cup.toml, env-var resolution
- `discover_connectors()` — entry-point discovery + auto-registration into Registry
- `check_health()` — pre-flight health checks for all registered connectors
- `HttpConnector` — built-in REST connector (stdlib urllib, zero deps)
- CLI: `cup connect --list`, `cup describe <connector>`, `--json` global flag

### Ring 9 — Marketplace ✅ (v0.9.0)

Connector discoverability + first four production connectors.

- **Marketplace infrastructure:**
  - `codeupipe.marketplace` package — `fetch_index`, `search`, `info`, `MarketplaceError`
  - JSON index with cache (1hr TTL, stale-on-error fallback), `CUP_MARKETPLACE_URL` env override
  - CLI: `cup marketplace search|info|install` with `--json` support
  - Trust tiers: verified (✅) / community (🔷)
  - `marketplace/index.json` — static index with 4 verified entries

- **First-party connectors** (each a standalone PyPI package in `connectors/`):

  | Package | Filters | SDK |
  |---|---|---|
  | `codeupipe-google-ai` | generate, generate_stream, embed, vision | google-genai |
  | `codeupipe-stripe` | checkout, subscription, webhook, customer | stripe |
  | `codeupipe-postgres` | query, execute, transaction, bulk_insert | psycopg |
  | `codeupipe-resend` | email, template | resend |

- 40 marketplace tests + 31 connector tests = 71 new tests

---

### Ring 10 — Secure Config ✅ (v0.10.0)

Platform-aware config validation and payload security at pipeline boundaries. Absorbed from the Zero-Trust Deploy Config (ZTDC) prototype.

- **Platform contracts:**
  - 23 JSON contract files in `deploy/contracts/` — AWS Lambda, Kubernetes, Docker, Vercel, and 19 more
  - `load_contract()`, `list_contracts()`, `validate_env()` — pure stdlib
  - `ContractError`, `ValidationResult` — clean error types
  - CLI: `cup config --list`, `cup config <contract> --var KEY=VALUE --env-file .env --json`

- **Secure payload:**
  - `seal_payload()` / `verify_payload()` — HMAC-SHA256 signing with timestamp + max_age expiry
  - `encrypt_data()` / `decrypt_data()` — PBKDF2 + authenticated encryption (stdlib only)
  - `SignFilter` / `VerifyFilter` — pipeline boundary signing
  - `EncryptFilter` / `DecryptFilter` — pipeline boundary encryption
  - `SecurePayloadError` — tamper, wrong key, expiry

- **Documentation:**
  - Archived completed blueprints (Ring 7–9) to `docs/archive/`
  - `docs/ring10-secure-config-blueprint.md` — design decisions, what was absorbed, what was left out

- **SPA obfuscation pipeline:**
  - 6-stage CUP pipeline in `deploy/obfuscate/` — scan → extract → obfuscate → reassemble → minify → write
  - Shells out to `javascript-obfuscator` + `html-minifier-terser` with graceful fallback
  - `ObfuscateConfig` — configurable tool options, reserved names, static copy
  - CLI: `cup obfuscate <src> <out> [--strict] [--html FILE...] [--static NAME...] [--json]`
  - Generalized from ZTDC prototype's `build.js`

- 81 new tests (18 contract + 21 secure + 42 obfuscate)

---

### Ring 11 — Polyglot Core ✅ (v0.11.0)

Language ports of the core primitives — same API, same mental model, idiomatic per language.

- **TypeScript port** (`ports/ts/`):
  - 8 source files: Payload, MutablePayload, Filter, StreamFilter, Pipeline, Valve, Tap, State, Hook
  - Promise-based async, AsyncIterable streaming, generic typing
  - Zero dependencies (TypeScript + vitest dev only)
  - Fluent builder API, serialize/deserialize, full feature parity with Python core
  - 88 tests (36 payload + 15 state + 4 valve + 33 pipeline)
  - Package: `@codeupipe/core` v0.1.0

- **Rust port** (`ports/rs/`):
  - 8 source files: Payload, MutablePayload, Value enum, Filter trait, StreamFilter trait, Pipeline, Valve, Tap, State, Hook
  - Send + Sync trait bounds — thread-safe by default
  - Zero external dependencies — stdlib only, WASM-compatible
  - AtomicBool for Valve, hand-rolled JSON serialize/deserialize
  - 59 tests (inline `#[cfg(test)]` modules)
  - Crate: `codeupipe-core` v0.1.0

- **Go port** (`ports/go/`):
  - 8 source files: Payload, MutablePayload, Filter, NamedFilter, StreamFilter, Pipeline, Valve, Tap, State, Hook, DefaultHook
  - Interfaces for Filter, StreamFilter, Tap, Hook (Go duck-typing)
  - Goroutine-based `AddParallel()` — real concurrency via `sync.WaitGroup`
  - Channel-based `Stream()` — idiomatic Go streaming
  - Zero external dependencies — stdlib only
  - Value semantics: Payload is a struct, not a pointer
  - 68 tests (24 payload + 14 state + 30 pipeline/valve)
  - Module: `github.com/codeuchain/codeupipe-core` (Go 1.21+)

- Blueprint: [docs/ring11-ai-frontend-blueprint.md](docs/ring11-ai-frontend-blueprint.md)

---

### Ring 12 — AI Suite ✅ (v0.12.0)

Full AI agent framework absorbed from the orchie project. Everything under `codeupipe.ai` — gated behind optional extras (`pip install codeupipe[ai]`). Zero-dep core untouched.

- **Agent SDK** (`codeupipe.ai.agent`):
  - `Agent`, `AgentConfig`, `AgentEvent`, `EventType`, `ServerDef`
  - Async generator-based event streaming (TURN_START, RESPONSE, TOOL_CALL, DONE, ERROR)
  - Inject, steer, and push directives for multi-turn conversations
  - Billing event tracking in verbose mode

- **Providers** (`codeupipe.ai.providers`):
  - `LanguageModelProvider` ABC — pluggable LLM backends
  - `CopilotProvider` — GitHub Copilot integration via copilot-sdk
  - Provider lifecycle: init → create_session → chat → cleanup

- **AI Filters** (`codeupipe.ai.filters`):
  - `InitProviderLink` — configure LLM provider from payload
  - `LanguageModelLink` — send messages to LLM, handle tool calls
  - `RegisterServersLink` — register MCP servers with the hub
  - `DiscoverByIntentLink` — intent-based capability discovery
  - Loop filters: `AgentLoopLink`, `ToolContinuationLink`, `ManageStateLink`, `BackchannelLink`, `ContextPruningLink`, `ContextAttributionLink`, `ConversationRevisionLink`, `UpdateIntentLink`, `RediscoverLink`, `ResumeSessionLink`, `SaveCheckpointLink`
  - Discovery filters: `EmbedQueryLink`, `CoarseSearchLink`, `FineRankLink`, `ValidateAvailabilityLink`, `FetchDefinitionsLink`, `GroupResultsLink`
  - Registration filters: `ScanFilesLink`, `ParseCapabilitiesLink`, `SyncRegistryLink`

- **AI Pipelines** (`codeupipe.ai.pipelines`):
  - `build_agent_session_chain()` — full agent lifecycle
  - `build_intent_discovery_chain()` — intent → capabilities
  - `build_capability_registration_chain()` — MCP server → registry
  - `build_file_registration_chain()` — local files → registry

- **Hooks** (`codeupipe.ai.hooks`):
  - `LoggingMiddleware` — per-step logging
  - `TimingMiddleware` — per-step elapsed time
  - `AuditProducer` — audit trail for AI operations

- **Hub** (`codeupipe.ai.hub`):
  - `ServerRegistry` / `create_default_hub()` — MCP server lifecycle management
  - `IOWrapper` — stdio/SSE transport abstraction

- **Discovery** (`codeupipe.ai.discovery`):
  - `CapabilityRegistry` — SQLite-backed capability store
  - `SnowflakeArcticEmbedder` — local embedding model (requires torch)
  - Capability types: tool, skill, instruction, plan, prompt, resource

- **TUI** (`codeupipe.ai.tui`):
  - `CopilotApp` — Textual-based rich terminal interface
  - Screens: chat, events, history
  - Widgets: input bar, message panel, event panel

- **Eval** (`codeupipe.ai.eval`):
  - Experiment runner, scenario management, metric computation
  - Baseline management, A/B comparisons, statistical analysis
  - SQLite storage, export, scoring, validation, reporting

- **CLI** — 7 new `cup ai-*` commands:
  - `cup ai-ask`, `cup ai-interactive`, `cup ai-tui`
  - `cup ai-discover`, `cup ai-sync`, `cup ai-register`, `cup ai-hub`

- **Extras** — optional dependency groups:
  - `codeupipe[ai]` — core AI deps (copilot-sdk, mcp, pydantic, numpy)
  - `codeupipe[ai-discovery]` — torch + transformers for embedding
  - `codeupipe[ai-tui]` — textual for TUI
  - `codeupipe[ai-full]` — everything

- 1221 AI tests (1221 pass without extras, remainder needs torch/textual/API keys)

- **Agent-Loop Template** (`cup init agent-loop`):
  - Full project scaffold for agentic turn-loop pattern (Claude Code / orchie flow)
  - `cup init agent-loop <name> --ai Copilot` → providers/, tools/, skills/, prompts/, sessions/, config/
  - Recipe: `agent-loop.json` — 5 session steps + 14-filter turn pipeline + 3 hooks
  - 4-layer system prompt, MCP hub config, context budget management, `__follow_up__` convention
  - `main.py` entry point with one-shot and interactive modes
  - 32 template-specific tests in `tests/test_agent_loop_template.py`

- Blueprint: [docs/ring12-ai-suite-blueprint.md](docs/ring12-ai-suite-blueprint.md)

---

## What's Next — Open Directions

Everything below is **unscheduled**. These are the natural next moves given what exists, not commitments. Pick what creates the most value and build it.

### Harden & Ship (v1.0 candidate)

The framework has 12 rings, 3351 Python tests + 215 polyglot tests, and a connector ecosystem. A v1.0 signals stability.

| Work | What It Means |
|---|---|
| **API stability audit** | Lock down public interfaces — breaking changes are versioned after this |
| **Documentation site** | Real docs (mkdocs/sphinx), not just INDEX.md. Tutorials, API reference, connector authoring guide |
| **PyPI presence for connectors** | Actually publish codeupipe-google-ai, codeupipe-stripe, etc. to PyPI |
| **Integration test suite** | Real SDK calls against sandbox accounts (Stripe test mode, Resend test domain, etc.) |
| **Error message polish** | Every user-facing error should guide them to the fix |

### Expand the Connector Catalog

More connectors follow the exact same pattern. Each is an independent package.

| Category | Candidates |
|---|---|
| **AI** | Anthropic, Ollama, Hugging Face |
| **Payments** | PayPal, LemonSqueezy |
| **Auth** | Auth0, Clerk, Supabase Auth, Firebase Auth, JWT validation |
| **Email** | SendGrid, Postmark, SES, Mailgun |
| **Storage** | S3, GCS, Azure Blob, Supabase Storage |
| **Database** | MySQL, SQLite, DynamoDB, MongoDB |
| **Cache** | Redis, Memcached |
| **Search** | Algolia, Meilisearch, Elasticsearch |
| **Notifications** | Twilio (SMS), Pusher, OneSignal |

### Cloud Deploy Adapters

The deploy protocol exists (Ring 7). These are new adapters plugging into it.

| Adapter | What It Does |
|---|---|
| **AWS Lambda** | Pipeline → Lambda handler + SAM/CDK template |
| **AWS ECS/Fargate** | Long-running/streaming pipelines → task definition |
| **Azure Functions** | Pipeline → Azure Function trigger |
| **Azure Container Apps** | Streaming pipelines → ACA deployment |
| **GCP Cloud Run** | Pipeline → containerized Cloud Run service |
| **Fly.io / Railway** | Indie/startup speed deploys |

### Developer Experience

| Feature | What It Does |
|---|---|
| **`cup studio`** | Visual pipeline builder — local web UI or VS Code extension |
| **Pipeline hub** | Shareable pipeline configs: `cup install recipe-name` |
| **Organization registries** | Private Registry servers for enterprise teams |
| **Richer recipes** | Recipes that auto-resolve connector dependencies from the marketplace |

### Polyglot Runtime (In Progress → Ring 11)

Write pipeline configs once, run them in any language. The codeuchain vision.

| Feature | What It Does | Status |
|---|---|---|
| **TypeScript runtime** | Browser/edge pipelines (GH Pages, CF Workers, Deno) | ✅ `ports/ts/` — 88 tests |
| **Rust runtime** | WASM, desktop, performance-critical workloads | ✅ `ports/rs/` — 59 tests |
| **Go runtime** | Concurrent executor for cloud infrastructure | ✅ `ports/go/` — 68 tests |
| **Wire protocol spec** | Language-agnostic Payload/Filter/Pipeline serialization | 🔜 Planned |
| **Cross-runtime orchestration** | Python + Rust + Go + TS filters in one pipeline | 🔜 Planned |
| **WASM filter support** | Compile Rust filters to WASM, run in any runtime | 🔜 Planned |

---

## Architecture Snapshot (v0.12.0)

```
codeupipe/
├── core/           Ring 1-4,10 Payload, Filter, Tap, Hook, StreamFilter, Valve,
│                              Pipeline, State, Event, Govern, Secure
├── distribute/     Ring 5     RemoteFilter, Checkpoint, Source, WorkerPool
├── deploy/         Ring 7,10  Adapters, Recipes, Init, Contracts (25 platforms)
├── connect/        Ring 8     ConnectorConfig, discover_connectors, HttpConnector
├── marketplace/    Ring 9     fetch_index, search, info, marketplace CLI
├── auth/           Ring 8     Credential, AuthProvider, TokenVault, ProxyToken
├── ai/             Ring 12    Agent SDK, Providers, Filters, Pipelines, Hooks,
│                              Hub, Discovery, TUI, Eval (optional extras)
├── linter/         Ring 1     Dogfooded lint/coverage/doc-check pipelines
├── converter/      Ring 2     Config pipeline assembly helpers
├── registry.py     Ring 2     Registry, cup_component, default_registry
├── testing.py      Ring 1     run_filter, run_pipeline, assert_payload, mock_filter
└── cli/            Ring 1+    22+ commands: new, list, bundle, lint, coverage,
                               report, doc-check, run, deploy, recipe, init,
                               connect, describe, marketplace, config,
                               ai-ask, ai-interactive, ai-tui, ai-discover,
                               ai-sync, ai-register, ai-hub

connectors/                    Ring 9 — standalone PyPI packages
├── codeupipe-google-ai/       4 filters (generate, stream, embed, vision)
├── codeupipe-stripe/          4 filters (checkout, subscription, webhook, customer)
├── codeupipe-postgres/        4 filters (query, execute, transaction, bulk_insert)
└── codeupipe-resend/          2 filters (email, template)

ports/                         Ring 11 — polyglot core implementations
├── ts/                        TypeScript — @codeupipe/core (88 tests)
│   └── src/                   Payload, Filter, StreamFilter, Pipeline, Valve, Tap, State, Hook
├── rs/                        Rust — codeupipe-core (59 tests)
│   └── src/                   Payload, Value, Filter, StreamFilter, Pipeline, Valve, Tap, State, Hook
└── go/                        Go — github.com/codeuchain/codeupipe-core (68 tests)
    └── codeupipe/             Payload, Filter, StreamFilter, Pipeline, Valve, Tap, State, Hook
```

---

## Principles

### What We Will NOT Build

- **Not a scheduler.** Airflow/Prefect/Dagster schedule tasks. codeupipe is the logic *inside* the task.
- **Not a message broker.** Kafka/RabbitMQ move messages. codeupipe *consumes from* them via source adapters.
- **Not an ORM.** Database filters are thin wrappers, not a query builder.
- **Not a web framework.** Flask/FastAPI serve HTTP. codeupipe pipelines are the handler logic behind a route.
- **Zero-dep core, always.** Connectors have their SDK deps. The core stays zero dependencies in every language — Python stdlib, TS no npm deps, Rust no crates, Go no modules.

### What We Always Do

- Every ring is tested, documented, and shipped before the next starts.
- `cup doc-check` + `cup lint` enforced by pre-commit hook.
- Trust but verify — tests hit real services where possible, mocks where necessary.
- Each ring builds on the previous. No skipping.
