# @codeupipe/core — TypeScript

TypeScript port of the codeupipe core pipeline primitives. Zero dependencies.

**Python** is for prototypes + backend. **TypeScript** is for web + browser. **Rust** is for WASM + desktop. **Go** is for cloud.

## Quick Start

```typescript
import { Payload, Pipeline, type Filter } from "@codeupipe/core";

class Greet implements Filter {
  async call(payload: Payload) {
    const name = payload.get("name") as string;
    return payload.insert("greeting", `Hello, ${name}!`);
  }
}

const pipeline = new Pipeline()
  .addFilter(new Greet(), "greet");

const result = await pipeline.run(new Payload({ name: "World" }));
console.log(result.get("greeting")); // "Hello, World!"
```

## Core Types

| Type | Role |
|------|------|
| `Payload<T>` | Immutable data container |
| `MutablePayload<T>` | Mutable sibling for bulk edits |
| `Filter<TIn, TOut>` | Processing unit — `call(payload) → Promise<Payload>` |
| `StreamFilter<TIn, TOut>` | Streaming — `stream(chunk)` yields 0..N |
| `Pipeline<TIn, TOut>` | Orchestrator — `.run()` / `.stream()` |
| `Valve<TIn, TOut>` | Conditional gate — filter + predicate |
| `Tap<T>` | Read-only observer — `.observe(payload)` |
| `State` | Execution metadata |
| `Hook<T>` | Lifecycle — before / after / onError |

## Tests

```bash
npm test          # vitest run
npm run test:watch # vitest watch mode
```
