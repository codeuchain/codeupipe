# Ring 11 — Polyglot Core & AI Frontend Blueprint

## Vision

codeupipe becomes a **polyglot pipeline runtime**. The core primitives — Payload, Filter, Pipeline, Valve, Tap, State, Hook — are implemented in four languages, each optimized for its domain:

| Language | Domain | Status |
|----------|--------|--------|
| **Python** | Prototypes, backend pipelines, AI connectors | ✅ Complete (Rings 1–10) |
| **TypeScript** | Web, browser, GH Pages SPA | ✅ Built — `ports/ts/` — 88 tests |
| **Rust** | WASM, desktop, performance-critical | ✅ Built — `ports/rs/` — 59 tests |
| **Go** | Cloud infrastructure, concurrent services | ✅ Built — `ports/go/` — 68 tests |

The **GitHub Pages prototype** runs pipelines entirely in the browser using codeupipe-ts — no backend server needed for the prototype. AI workflow integration comes later via backend APIs.

---

## What Was Built

### codeupipe-ts (TypeScript Core)

Location: `ports/ts/`

8 source files, 4 test files, **88 tests passing**.

```
ports/ts/
├── package.json             # @codeupipe/core v0.1.0
├── tsconfig.json
├── vitest.config.ts
├── src/
│   ├── index.ts             # Public API re-exports
│   ├── payload.ts           # Payload<T>, MutablePayload<T>
│   ├── filter.ts            # Filter<TIn, TOut> interface
│   ├── stream_filter.ts     # StreamFilter<TIn, TOut> interface
│   ├── pipeline.ts          # Pipeline orchestrator
│   ├── valve.ts             # Valve — conditional gate
│   ├── tap.ts               # Tap interface
│   ├── state.ts             # State tracker
│   └── hook.ts              # Hook interface
└── tests/
    ├── payload.test.ts      # 36 tests — immutability, merge, serialize, lineage
    ├── state.test.ts        # 15 tests — tracking, diff, reset
    ├── valve.test.ts        # 4 tests — predicate gating
    └── pipeline.test.ts     # 33 tests — batch, streaming, hooks, parallel, nesting
```

**Key characteristics:**
- Zero dependencies (TypeScript + vitest dev only)
- `Promise`-based async (all filters return `Promise<Payload>`)
- `AsyncIterable` streaming (StreamFilter yields via `async function*`)
- Generic typing: `Payload<T extends Record<string, unknown>>`
- Immutable Payload by default, MutablePayload for performance-critical paths
- Fluent builder API: `pipeline.addFilter().addTap().useHook().observe()`
- Full serialize/deserialize for network transport
- Feature parity with Python core (batch, streaming, parallel, nesting, hooks, taps, valves)

### codeupipe-core (Rust Core)

Location: `ports/rs/`

8 source files, **59 tests passing** (inline `#[cfg(test)]` modules).

```
ports/rs/
├── Cargo.toml               # codeupipe-core v0.1.0
├── src/
│   ├── lib.rs               # Public API re-exports
│   ├── payload.rs           # Payload, MutablePayload, Value enum
│   ├── filter.rs            # Filter trait (Send + Sync)
│   ├── stream_filter.rs     # StreamFilter trait
│   ├── pipeline.rs          # Pipeline orchestrator
│   ├── valve.rs             # Valve — conditional gate (AtomicBool)
│   ├── tap.rs               # Tap trait
│   ├── state.rs             # State tracker
│   └── hook.rs              # Hook trait
└── README.md
```

**Key characteristics:**
- Zero external dependencies — stdlib only
- `Value` enum for dynamic typing: `Int(i64)`, `Float(f64)`, `Str(String)`, `Bool(bool)`, `List(Vec<Value>)`, `Map(HashMap<String, Value>)`, `Null`
- Synchronous `Filter::call(&self, Payload) → Result<Payload, Error>` (async via tokio wrapping in application layer)
- `Send + Sync` trait bounds — thread-safe by default
- `AtomicBool` for Valve skip tracking — no unsafe code
- Hand-rolled JSON serialize/deserialize — no serde dependency
- WASM-compatible: `cargo build --target wasm32-unknown-unknown`
- Streaming via `Vec<Payload>` (iterators; true async streaming wraps with channels)

### codeupipe-core (Go Core)

Location: `ports/go/`

8 source files, 3 test files, **68 tests passing**.

```
ports/go/
├── go.mod                    # github.com/codeuchain/codeupipe-core (Go 1.21+)
├── README.md
└── codeupipe/
    ├── payload.go            # Payload, MutablePayload (value semantics)
    ├── filter.go             # Filter, NamedFilter interfaces
    ├── stream_filter.go      # StreamFilter interface
    ├── pipeline.go           # Pipeline orchestrator (goroutines + channels)
    ├── valve.go              # Valve — conditional gate
    ├── tap.go                # Tap interface
    ├── state.go              # State tracker
    ├── hook.go               # Hook interface, DefaultHook embedding
    ├── payload_test.go       # 24 tests — immutability, merge, serialize, lineage
    ├── state_test.go         # 14 tests — tracking, diff, reset
    └── pipeline_test.go      # 30 tests — batch, streaming, hooks, parallel, nesting, valves
```

**Key characteristics:**
- Zero external dependencies — stdlib only (`encoding/json`, `sync`, `reflect`, `time`)
- Interfaces for Filter, StreamFilter, Tap, Hook (Go duck-typing)
- Goroutine-based `AddParallel()` — real concurrency via `sync.WaitGroup`
- Channel-based `Stream()` — idiomatic Go streaming
- `any` for dynamic values (Go 1.18+ alias for `interface{}`)
- Value semantics: `Payload` is a struct, not a pointer
- `DefaultHook` for no-op embedding — override only what you need
- Fluent builder API: `pipeline.AddFilter().AddTap().UseHook().Observe()`

---

## Prototype Architecture (Browser-Only)

The prototype runs **entirely in the browser** using codeupipe-ts. No backend server needed.

```
┌────────────────────────────────────────────────────────────────┐
│  GitHub Pages (Static Site)                                    │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  codeupipe-ts Pipeline (in-browser)                     │   │
│  │                                                         │   │
│  │  Payload({ prompt: "..." })                             │   │
│  │    → SanitizeInput (Filter)                             │   │
│  │    → BuildAPIRequest (Filter)                           │   │
│  │    → FetchFromAPI (Filter) — calls Gemini/OpenAI/etc.   │   │
│  │    → ParseResponse (Filter)                             │   │
│  │    → RenderToDOM (Filter)                               │   │
│  │    → UsageLog (Tap)                                     │   │
│  │                                                         │   │
│  │  Result: Payload({ response: "...", rendered: true })   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  No backend. API key in browser (dev/prototype only).          │
│  Production moves key to backend + TokenVault.                 │
└────────────────────────────────────────────────────────────────┘
```

For the prototype, the browser pipeline calls AI APIs directly. This is fine for development. Production adds a backend layer with TokenVault to protect API keys.

---

## What Already Exists (Backend Infrastructure for Later)

| Asset | Location | What It Gives Us |
|-------|----------|-----------------|
| **ZTDC prototype** | `zero-trust-deploy-config/` on GH Pages | Proven SPA + CF Worker + GitHub OAuth pattern |
| **CF Worker API** | `ztdc-github-oauth` (Cloudflare) | 41-function API gateway, CORS, JWT sessions |
| **Google AI connector** | `connectors/codeupipe-google-ai/` | Gemini generate, stream, embed, vision |
| **Token Vault** | `auth/token_vault.py` | Proxy tokens — never expose real credentials |
| **Platform contracts** | `deploy/contracts/` | 25 JSON schemas for deployment validation |

These activate when we move from prototype to production.

---

## Production Architecture (After Prototype)

```
Browser ─ fetch/SSE ─→ CF Worker (edge) ─→ Oracle VM (compute)
                        ├── Auth/JWT           ├── codeupipe (Python)
                        ├── CORS               ├── Gemini API calls
                        ├── Rate limiting      ├── Postgres
                        └── KV cache           └── TokenVault
```

---

## Cross-Port API Comparison

All ports implement the same 8 primitives with language-idiomatic APIs:

| Feature | Python | TypeScript | Rust |
|---------|--------|------------|------|
| Payload create | `Payload({"x": 1})` | `new Payload({ x: 1 })` | `Payload::new().insert("x", Value::Int(1))` |
| Get value | `p.get("x")` | `p.get("x")` | `p.get("x")` |
| Insert (immutable) | `p.insert("y", 2)` | `p.insert("y", 2)` | `p.insert("y", Value::Int(2))` |
| Mutable | `p.with_mutation()` | `p.withMutation()` | `p.with_mutation()` |
| Freeze mutable | `mp.to_immutable()` | `mp.toImmutable()` | `mp.to_immutable()` |
| Filter | `async def call(self, payload)` | `async call(payload): Promise<Payload>` | `fn call(&self, payload: Payload) → Result<Payload>` |
| Pipeline run | `await pipeline.run(payload)` | `await pipeline.run(payload)` | `pipeline.run(payload)?` |
| Pipeline stream | `async for p in pipeline.stream(src)` | `for await (const p of pipeline.stream(src))` | `pipeline.stream(vec![...])?` |
| Valve | `Valve(name, filter, predicate)` | `new Valve(name, filter, predicate)` | `Valve::new(name, Box::new(filter), predicate)` |
| State access | `pipeline.state` | `pipeline.state` | `pipeline.state()` |
| Serialize | `payload.serialize()` | `payload.serialize()` | `payload.serialize()` |
| Deserialize | `Payload.deserialize(bytes)` | `Payload.deserialize(bytes)` | `Payload::deserialize(&bytes)?` |

---

## Phase Plan

### Phase 0 — Polyglot Core ✅
- [x] Port 8 core primitives to TypeScript (`ports/ts/`, 88 tests)
- [x] Port 8 core primitives to Rust (`ports/rs/`, 59 tests)
- [x] Zero external dependencies in both ports
- [x] Full test coverage on both ports

### Phase 1 — SPA Prototype (Browser-Only)
- [ ] Create GitHub Pages site (static HTML + codeupipe-ts)
- [ ] Build browser pipeline: prompt → API call → render
- [ ] Direct AI API calls from browser (dev mode)
- [ ] Pipeline state visualization in UI
- [ ] No backend needed — pure client-side

### Phase 2 — Production Backend
- [ ] Oracle VM setup (Always Free ARM, 24GB RAM)
- [ ] Python API server with codeupipe pipelines
- [ ] CF Worker proxy with auth + rate limiting
- [ ] TokenVault integration (no API keys in browser)
- [ ] SSE streaming: backend → browser

### Phase 3 — Go Port (Cloud Runtime) ✅
- [x] Port 8 core primitives to Go (`ports/go/`)
- [x] Goroutine-based parallel execution
- [x] Channel-based streaming
- [ ] Cloud-native: Kubernetes sidecar, Cloud Run handler
- [ ] gRPC filter communication for cross-process pipelines

### Phase 4 — Cross-Runtime Orchestration
- [ ] Wire protocol spec (language-agnostic Payload serialization)
- [ ] Python filters + Rust filters + Go filters in one pipeline
- [ ] WASM filter compilation (Rust → WASM → browser)
- [ ] Pipeline hub: shareable configs that run in any runtime

---

## Open Questions

1. **Monorepo layout decided**: `ports/ts/`, `ports/rs/`, and `ports/go/` inside the codeupipe repo. One repo, all languages.

2. **codeupipe-ts publish**: npm as `@codeupipe/core` or bundled into the SPA? Start bundled, publish to npm when stable.

3. **Rust WASM**: Compile `codeupipe-core` to WASM for in-browser Rust pipelines? Possible but TypeScript is simpler for browser. WASM for performance-critical filters.

4. **Go port scope**: Same 8 primitives. Goroutines for `AddParallel()`. Channels for `Stream()`. `encoding/json` for serialize. Zero deps. ✅ Done — 68 tests.

---

## Test Summary

| Port | Tests | Status |
|------|-------|--------|
| **Python** | 2097+ | ✅ Rings 1–10 complete |
| **TypeScript** | 88 | ✅ All passing |
| **Rust** | 59 | ✅ All passing |
| **Go** | 68 | ✅ All passing |
| **Total** | **2312+** | |

---

## Key Insight

The pipeline model is **language-agnostic**. `Payload → Filter → Pipeline` works identically in Python, TypeScript, Rust, and Go. The core is ~450 LOC in TS, ~600 LOC in Rust, ~500 LOC in Go, ~1200 LOC in Python. The difference is docstrings and type ceremony, not logic.

Each language earns its keep:
- **Python**: rapid prototyping, AI connectors, backend orchestration
- **TypeScript**: browser pipelines, SPA rendering, web APIs
- **Rust**: WASM modules, desktop apps, performance-critical filters
- **Go**: cloud services, concurrent infrastructure, Kubernetes operators
