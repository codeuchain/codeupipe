# codeupipe-core — Rust

Rust port of the codeupipe core pipeline primitives. Zero external dependencies. WASM-compatible.

**Python** is for prototypes + backend. **TypeScript** is for web + browser. **Rust** is for WASM + desktop. **Go** is for cloud.

## Quick Start

```rust
use codeupipe_core::{Payload, Pipeline, Filter, Value};

struct Greet;
impl Filter for Greet {
    fn call(&self, payload: Payload) -> Result<Payload, Box<dyn std::error::Error + Send + Sync>> {
        let name = payload.get("name").and_then(|v| v.as_str()).unwrap_or("World");
        Ok(payload.insert("greeting", Value::Str(format!("Hello, {}!", name))))
    }
    fn name(&self) -> &str { "Greet" }
}

fn main() {
    let mut pipeline = Pipeline::new()
        .add_filter(Box::new(Greet), "greet");

    let result = pipeline.run(
        Payload::new().insert("name", Value::Str("World".to_string()))
    ).unwrap();

    println!("{}", result.get("greeting").unwrap().as_str().unwrap());
    // "Hello, World!"
}
```

## Core Types

| Type | Role |
|------|------|
| `Payload` | Immutable data container |
| `MutablePayload` | Mutable sibling for bulk edits |
| `Value` | Dynamic value enum (Int, Float, Str, Bool, List, Map, Null) |
| `Filter` | Processing trait — `call(payload) → Result<Payload>` |
| `StreamFilter` | Streaming trait — `stream(chunk) → Vec<Payload>` |
| `Pipeline` | Orchestrator — `.run()` / `.stream()` |
| `Valve` | Conditional gate — filter + predicate |
| `Tap` | Read-only observer — `.observe(&payload)` |
| `State` | Execution metadata |
| `Hook` | Lifecycle — before / after / on_error |

## Tests

```bash
cargo test          # Run all tests
cargo test -- -v    # Verbose output
```

## WASM

The crate has no external dependencies and avoids platform-specific APIs,
making it compatible with `wasm32-unknown-unknown` targets:

```bash
cargo build --target wasm32-unknown-unknown
```
