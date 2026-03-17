# codeupipe-core (Go)

Go port of codeupipe's 8 core pipeline primitives. Zero external dependencies — stdlib only.

**Go is for cloud infrastructure** — concurrent services, Kubernetes operators, CLI tools.

## Quick Start

```go
package main

import (
    "fmt"
    cup "github.com/codeuchain/codeupipe-core/codeupipe"
)

// A simple filter that doubles a number.
type DoubleFilter struct{}

func (f *DoubleFilter) Call(p cup.Payload) (cup.Payload, error) {
    n, _ := p.Get("n").(float64)
    return p.Insert("n", n*2), nil
}

func main() {
    pipeline := cup.NewPipeline().
        AddFilter(&DoubleFilter{}, "Double")

    result, err := pipeline.Run(cup.NewPayload(map[string]any{"n": float64(5)}))
    if err != nil {
        panic(err)
    }
    fmt.Println(result.Get("n")) // 10
}
```

## Core Types

| Type | File | Role |
|------|------|------|
| `Payload` | payload.go | Immutable data container |
| `MutablePayload` | payload.go | Mutable sibling for bulk edits |
| `Filter` | filter.go | Processing interface — `Call(payload) (Payload, error)` |
| `StreamFilter` | stream_filter.go | Streaming — `Stream(chunk) ([]Payload, error)` |
| `Pipeline` | pipeline.go | Orchestrator — `.Run()` / `.Stream()` |
| `Valve` | valve.go | Conditional gate — filter + predicate |
| `Tap` | tap.go | Read-only observer — `.Observe(payload)` |
| `State` | state.go | Execution metadata |
| `Hook` | hook.go | Lifecycle — `Before` / `After` / `OnError` |
| `DefaultHook` | hook.go | No-op Hook for embedding |

## Go-Idiomatic Design

- **Interfaces** for Filter, StreamFilter, Tap, Hook (duck-typed)
- **Goroutines** for `AddParallel()` — real concurrency via `sync.WaitGroup`
- **Channels** for `Stream()` — idiomatic Go streaming
- **`any`** for dynamic values (Go 1.18+ alias for `interface{}`)
- **`encoding/json`** for serialization (stdlib)
- **Zero external modules** — stdlib only

## Tests

```bash
cd ports/go && go test -v ./...
```

68 tests covering Payload, MutablePayload, State, Valve, Pipeline (batch + streaming).

## Constraints

- **Go 1.21+** minimum (uses `maps`, `slices` stdlib packages)
- **Zero external dependencies** — stdlib only
- **Value semantics** — Payload is a value type (struct), not a pointer
