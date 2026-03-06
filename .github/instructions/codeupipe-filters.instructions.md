---
applyTo: 'codeupipe/**/*.py'
description: 'How to write a codeupipe Filter — class structure, Payload contract, naming, file layout'
---

# Writing a Filter

## The Pattern

Every filter is a class with a `.call(payload) → Payload` method. Sync or async — Pipeline handles both.

```python
from codeupipe import Payload

class MyFilter:
    """One-sentence description of what this filter does."""

    def call(self, payload: Payload) -> Payload:
        # Read from payload
        value = payload.get("input_key")

        # Do one thing
        result = transform(value)

        # Write to payload and return
        return payload.set("output_key", result)
```

## Rules

1. **One filter per file.** `CheckNaming` → `check_naming.py`.
2. **PascalCase** for filter class names. **snake_case** for filenames.
3. **Payload in, Payload out.** Never mutate — always return `payload.set(...)`.
4. **Do one thing.** If a filter does two things, split it into two filters.
5. **Read with `.get()`, write with `.set()`.** Payload is immutable.
6. **Raise on failure.** Throw exceptions for unrecoverable errors — Pipeline catches them in State.
7. **No side effects in `.call()`** unless that IS the purpose (e.g., a Tap's `.observe()`).

## Async Filters

Same pattern, just `async def`:

```python
class AsyncFetcher:
    async def call(self, payload: Payload) -> Payload:
        data = await fetch(payload.get("url"))
        return payload.set("response", data)
```

## StreamFilters

Yield 0..N output chunks:

```python
class Splitter:
    async def stream(self, payload: Payload):
        for item in payload.get("items"):
            yield payload.set("current", item)
```

## Naming Conventions

| Component | Class Name | File Name | Test File |
|-----------|-----------|-----------|-----------|
| Filter | `ValidateEmail` | `validate_email.py` | `test_validate_email.py` |
| StreamFilter | `SplitChunks` | `split_chunks.py` | `test_split_chunks.py` |
| Tap | `AuditLog` | `audit_log.py` | `test_audit_log.py` |
| Hook | `TimingHook` | `timing_hook.py` | `test_timing_hook.py` |

## Registering in `__init__.py`

After creating a filter, add it to the parent package's `__init__.py` and `__all__`:

```python
from .validate_email import ValidateEmail
```

Keep imports and `__all__` entries **alphabetically sorted**.
