---
applyTo: 'codeupipe/linter/**'
description: 'Every analysis tool in codeupipe is itself a CUP pipeline — the dogfooding pattern for building new linter pipelines'
---

# Linter Dogfooding Pattern

## Principle

Every analysis tool (lint, coverage, report, doc-check) is built as a **CUP pipeline** — Filter classes composed into a Pipeline, reading/writing Payload. We eat our own cooking.

## Building a New Analysis Pipeline

### 1. Design the Filter Chain

Each filter does one thing. Data flows through Payload keys:

```
ScanDirectory → payload["files"]
    ↓
CheckNaming → payload["issues"] (appended)
    ↓
CheckStructure → payload["issues"] (appended)
    ↓
AssembleReport → payload["report"]
```

### 2. Write Each Filter (one file per filter in `codeupipe/linter/`)

```python
# codeupipe/linter/scan_something.py
from codeupipe import Payload

class ScanSomething:
    """One-sentence description."""

    def call(self, payload: Payload) -> Payload:
        directory = payload.get("directory")
        # ... analysis logic ...
        return payload.set("scan_results", results)
```

### 3. Wire the Pipeline Builder

```python
# codeupipe/linter/my_pipeline.py
from codeupipe import Pipeline
from .scan_something import ScanSomething
from .check_something import CheckSomething

def build_my_pipeline() -> Pipeline:
    return Pipeline([
        ScanSomething(),
        CheckSomething(),
    ])
```

### 4. Export from `codeupipe/linter/__init__.py`

Add imports and `__all__` entries, **alphabetically sorted**.

### 5. Add a CLI Wrapper

See `codeupipe-cli.instructions.md` for the three-step pattern.

## Existing Pipelines

| Pipeline | Filters | Purpose |
|----------|---------|---------|
| `build_lint_pipeline()` | ScanDirectory → CheckNaming → CheckStructure → CheckProtocols → CheckTests → CheckBundle | Standards violations |
| `build_coverage_pipeline()` | ScanDirectory → ScanTests → ScanComponents → MapCoverage → ReportGaps | Test coverage mapping |
| `build_report_pipeline()` | ScanDirectory → ScanTests → ScanComponents → MapCoverage → DetectOrphans → GitHistory → AssembleReport | Full health report |
| `build_doc_check_pipeline()` | ScanDocs → ResolveRefs → CheckSymbols → DetectDrift → AssembleDocReport | Doc freshness |

## Key Payload Conventions

- `"directory"` — input: path to analyze (string)
- `"tests_dir"` — input: path to tests directory (string, default `"tests"`)
- `"issues"` — accumulated lint issues, list of `(rule_id, severity, filepath, message)`
- `"report"` / `"doc_report"` — final assembled output dict
