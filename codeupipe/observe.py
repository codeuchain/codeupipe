"""
codeupipe.observe — Production observability via Taps.

Provides pre-built taps for capturing pipeline data in production,
exporting captured payloads for test replay, and recording run metrics.
Zero external dependencies.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from codeupipe.core.payload import Payload
from codeupipe.core.state import State

__all__ = [
    "CaptureTap",
    "MetricsTap",
    "RunRecord",
    "save_run_record",
    "load_run_records",
    "export_captures_for_testing",
]


# ── CaptureTap — record payloads passing through ────────────────────


class CaptureTap:
    """Tap that captures payload snapshots for replay and debugging.

    Attach to a pipeline to silently record every payload that passes through.
    Captured data can be exported as test fixtures.

    Usage:
        tap = CaptureTap(name="after_validate")
        pipeline.add_tap(tap, name="capture_after_validate")
        result = await pipeline.run(payload)
        # tap.captures is now a list of payload dicts
    """

    def __init__(self, name: str = "capture", max_captures: int = 1000):
        self.name = name
        self.captures: List[Dict[str, Any]] = []
        self._max = max_captures

    async def observe(self, payload: Payload) -> None:
        if len(self.captures) < self._max:
            self.captures.append(payload.to_dict())

    def clear(self) -> None:
        self.captures.clear()

    def export_json(self) -> str:
        return json.dumps(self.captures, indent=2, default=str)


# ── MetricsTap — lightweight timing + counting ──────────────────────


class MetricsTap:
    """Tap that records lightweight metrics: invocation count and timestamps.

    Usage:
        tap = MetricsTap(name="after_transform")
        pipeline.add_tap(tap, name="metrics_after_transform")
    """

    def __init__(self, name: str = "metrics"):
        self.name = name
        self.count: int = 0
        self.timestamps: List[float] = []

    async def observe(self, payload: Payload) -> None:
        self.count += 1
        self.timestamps.append(time.monotonic())

    def reset(self) -> None:
        self.count = 0
        self.timestamps.clear()


# ── Run Record — persist pipeline run results ────────────────────────

_RUNS_DIR = Path(".cup") / "runs"


class RunRecord:
    """A serializable record of a single pipeline run."""

    def __init__(
        self,
        pipeline_name: str,
        state: State,
        *,
        input_keys: Optional[List[str]] = None,
        output_keys: Optional[List[str]] = None,
        duration: Optional[float] = None,
        success: bool = True,
        error: Optional[str] = None,
    ):
        self.pipeline_name = pipeline_name
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.executed = list(state.executed)
        self.skipped = list(state.skipped)
        self.error_count = len(state.errors)
        self.timings = dict(state.timings)
        self.chunks = dict(state.chunks_processed)
        self.input_keys = input_keys or []
        self.output_keys = output_keys or []
        self.duration = duration
        self.success = success
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline": self.pipeline_name,
            "timestamp": self.timestamp,
            "success": self.success,
            "duration": self.duration,
            "executed": self.executed,
            "skipped": self.skipped,
            "error_count": self.error_count,
            "error": self.error,
            "timings": self.timings,
            "chunks": self.chunks,
            "input_keys": self.input_keys,
            "output_keys": self.output_keys,
        }


def save_run_record(record: RunRecord, runs_dir: Optional[Path] = None) -> Path:
    """Save a run record to .cup/runs/ as JSON. Returns the file path."""
    directory = runs_dir or _RUNS_DIR
    directory.mkdir(parents=True, exist_ok=True)

    # Filename: {pipeline}_{timestamp}.json
    ts = record.timestamp.replace(":", "-").replace("+", "p")
    filename = f"{record.pipeline_name}_{ts}.json"
    filepath = directory / filename
    filepath.write_text(json.dumps(record.to_dict(), indent=2, default=str))
    return filepath


def load_run_records(
    runs_dir: Optional[Path] = None,
    pipeline: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Load recent run records from .cup/runs/, newest first."""
    directory = runs_dir or _RUNS_DIR
    if not directory.exists():
        return []

    files = sorted(directory.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    records: List[Dict[str, Any]] = []
    for f in files:
        if len(records) >= limit:
            break
        try:
            data = json.loads(f.read_text())
            if pipeline and data.get("pipeline") != pipeline:
                continue
            data["_file"] = str(f)
            records.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return records


# ── Export captures as test fixtures ─────────────────────────────────


def export_captures_for_testing(
    captures: List[Dict[str, Any]],
    output_path: str,
    fixture_name: str = "captured_payloads",
) -> Path:
    """Export captured payloads as a Python test fixture file.

    Generates a pytest fixture module that yields the captured data,
    ready to replay through pipelines in tests.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        '"""Auto-generated test fixtures from production capture."""',
        "",
        "import pytest",
        "",
        "",
        f"@pytest.fixture",
        f"def {fixture_name}():",
        f'    """Captured production payloads for replay testing."""',
        f"    return {json.dumps(captures, indent=4, default=str)}",
        "",
    ]
    path.write_text("\n".join(lines))
    return path
