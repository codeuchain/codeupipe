---
applyTo: 'codeupipe/**,tests/**,examples/**'
description: 'codeupipe project architecture — package layout, module responsibilities, zero-dependency constraint'
---

# codeupipe Architecture

## Package Layout

```
codeupipe/
├── __init__.py          # Public API re-exports (Payload, Filter, Pipeline, etc.)
├── py.typed             # PEP 561 marker
├── core/                # Primitives: Payload, Filter, StreamFilter, Pipeline, Valve, Tap, State, Hook
├── utils/               # ErrorHandlingMixin, RetryFilter
├── converter/           # CodeUChain ↔ codeupipe migration tools
├── linter/              # All analysis pipelines (lint, coverage, report, doc-check)
├── testing.py           # Test helpers: run_filter, assert_payload, mock_filter, etc.
└── cli.py               # `cup` CLI: new, list, bundle, lint, coverage, report, doc-check
```

## Constraints

- **Zero external runtime dependencies.** stdlib only. No exceptions.
- **Python 3.9+** minimum. No walrus operators or 3.10+ syntax.
- **`py.typed`** — the package ships type annotations.

## Core Types (from `codeupipe.core`)

| Type | Role |
|------|------|
| `Payload` | Immutable data container flowing through pipelines |
| `MutablePayload` | Mutable sibling for performance-critical bulk edits |
| `Filter` | Processing unit — sync or async `.call(payload) → Payload` |
| `StreamFilter` | Streaming — async `.stream(payload)` yields 0..N chunks |
| `Pipeline` | Orchestrator — `.run()` for batch, `.stream()` for streaming |
| `Valve` | Conditional flow — gates a filter with a predicate |
| `Tap` | Non-modifying observation — sync or async `.observe(payload)` |
| `State` | Execution metadata — tracks executed, skipped, errors, chunks |
| `Hook` | Lifecycle — `before()` / `after()` / `on_error()` |

## Module Responsibilities

- **One class per file.** A filter named `CheckNaming` lives in `check_naming.py`.
- **Linter pipelines are CUP pipelines.** Every analysis tool (lint, coverage, report, doc-check) is itself a `Pipeline` composed of `Filter` classes. This is dogfooding.
- **`testing.py`** is a flat module (not a package). It provides `run_filter`, `run_pipeline`, `assert_payload`, `assert_keys`, `assert_state`, `mock_filter`, `mock_tap`, `mock_hook`, `cup_component`, `RecordingTap`, `RecordingHook`.
- **`cli.py`** contains scaffolding templates, the bundle engine, and all `cup` subcommand logic. Each subcommand delegates to a wrapper function that builds and runs a pipeline.
