---
applyTo: 'tests/**'
description: 'codeupipe testing conventions — file naming, codeupipe.testing helpers, RED→GREEN workflow, test structure'
---

# Testing Conventions

## File Naming

- Test file mirrors source: `check_naming.py` → `test_check_naming.py`
- Pipeline integration tests: `test_lint_pipeline.py`, `test_doc_check_pipeline.py`
- CLI tests: `test_doc_check_cli.py`, `test_cli.py`
- All test files live in `tests/` (flat — no subdirectories except `tests/converter/`)

## Use `codeupipe.testing` Helpers

```python
from codeupipe.testing import run_filter, run_pipeline, assert_payload, assert_keys, assert_state
```

### Testing a Filter

```python
from codeupipe.testing import run_filter, assert_payload

def test_my_filter_transforms_input():
    result = run_filter(MyFilter(), {"input": "raw"})
    assert_payload(result, output="transformed")
```

### Testing a Pipeline

```python
from codeupipe.testing import run_pipeline, assert_state

def test_pipeline_runs_clean():
    pipeline = build_my_pipeline()
    result = run_pipeline(pipeline, {"directory": str(tmp_path)})
    assert_state(result, executed=["MyFilterA", "MyFilterB"])
```

### Available Helpers

| Helper | Purpose |
|--------|---------|
| `run_filter(filter, data)` | Run a single filter, returns Payload |
| `run_pipeline(pipeline, data)` | Run a full pipeline, returns Payload |
| `assert_pipeline_streaming(pipeline, data)` | Collect stream chunks, returns list |
| `assert_payload(payload, **expected)` | Assert key=value pairs on payload |
| `assert_keys(payload, *keys)` | Assert keys exist on payload |
| `assert_state(payload, executed=[], skipped=[], errors=[])` | Assert State tracking |
| `mock_filter(name, **sets)` | Create a mock filter that sets payload keys |
| `mock_tap(name)` | Create a recording tap |
| `mock_hook(name)` | Create a recording hook |
| `cup_component(cls)` | Validate a class follows CUP component protocols |
| `RecordingTap` | Tap that records all observed payloads |
| `RecordingHook` | Hook that records all lifecycle calls |

## Test Structure

```python
class TestMyFilter:
    """Tests for MyFilter."""

    def test_happy_path(self, tmp_path):
        ...

    def test_edge_case(self, tmp_path):
        ...

    def test_error_condition(self):
        ...
```

- **`tmp_path`** fixture for filesystem tests. Never write to real project dirs.
- **Class-grouped** by the component under test.
- **Descriptive method names** — `test_<what_it_does>` not `test_1`.

## RED → GREEN Workflow

1. **RED**: Write failing tests first. Import the not-yet-existing class. Run pytest — confirm `ImportError` or assertion failures.
2. **GREEN**: Implement the minimum code to make tests pass.
3. **Verify**: Run full suite (`python3 -m pytest --tb=short -q`) — no regressions.

## Current Suite

909 tests across 48 files. Full suite runs in ~4 seconds.

```bash
python3 -m pytest --tb=short -q     # Quick summary
python3 -m pytest -v                # Verbose per-test
```
