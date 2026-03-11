"""
codeupipe.observe — Production observability via Taps.

Provides pre-built taps for capturing pipeline data in production,
exporting captured payloads for test replay, and recording run metrics.
Zero external dependencies.
"""

import json
import statistics
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from codeupipe.core.payload import Payload
from codeupipe.core.state import State

__all__ = [
    "CaptureTap",
    "InsightTap",
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


# ── InsightTap — accumulate stats across runs ────────────────────────


class InsightTap:
    """Tap that accumulates runtime statistics across many pipeline runs.

    Attach to any pipeline to silently gather throughput, latency percentiles,
    error rates, and observed payload keys over time.  Thread-safe.

    Unlike MetricsTap (counts + timestamps only), InsightTap computes
    aggregated statistics suitable for dashboards and reporting.

    Usage:
        tap = InsightTap()
        pipeline.add_tap(tap, name="insights")

        # ... many runs later ...
        print(tap.summary())
        tap.export_json("insights.json")

        # Toggle at runtime via TapSwitch — zero overhead when disabled
    """

    def __init__(self, name: str = "insight", max_durations: int = 10_000):
        self.name = name
        self._lock = threading.Lock()
        self._max_durations = max_durations
        self._total_runs: int = 0
        self._error_count: int = 0
        self._durations_ms: List[float] = []
        self._observed_keys: set = set()
        self._first_seen: Optional[float] = None
        self._last_seen: Optional[float] = None

    async def observe(self, payload: Payload) -> None:
        """Record one observation.  Called by Pipeline on every run."""
        now = time.monotonic()
        data = payload.to_dict()
        keys = set(data.keys())
        has_error = "_error" in data

        with self._lock:
            if self._first_seen is None:
                self._first_seen = now
            self._last_seen = now
            self._total_runs += 1
            if has_error:
                self._error_count += 1
            self._observed_keys.update(keys)

            # Estimate duration from time between consecutive observations
            # (best-effort — a Tap doesn't know step timing directly).
            # If the pipeline has observe(timing=True), users should read
            # State.timings for per-step detail.  InsightTap gives the
            # macro view: how fast are payloads flowing through this point?
            if len(self._durations_ms) > 0:
                # Duration since the *previous* observation at this tap
                prev = self._last_seen  # already updated above
                # We need the timestamp of the *previous* call.
                pass
            # Store the wall-clock time of this observation for throughput.
            # For duration, we measure the gap between consecutive observe()
            # calls — approximates "time between payloads at this tap point".
            if self._total_runs >= 2:
                # Gap between this and the previous observation
                gap_ms = 0.0  # calculated below
            # Simpler approach: record wall-clock at observe time and
            # derive durations from consecutive timestamps.
            self._durations_ms.append(now)
            if len(self._durations_ms) > self._max_durations:
                self._durations_ms = self._durations_ms[-self._max_durations:]

    def summary(self) -> Dict[str, Any]:
        """Return aggregated statistics as a dict."""
        with self._lock:
            total = self._total_runs
            errors = self._error_count

            if total == 0:
                return {
                    "name": self.name,
                    "total_runs": 0,
                    "error_count": 0,
                    "error_rate_pct": 0.0,
                    "throughput_per_sec": 0.0,
                    "avg_duration_ms": 0.0,
                    "min_duration_ms": 0.0,
                    "max_duration_ms": 0.0,
                    "p95_duration_ms": 0.0,
                    "p99_duration_ms": 0.0,
                    "observed_keys": sorted(self._observed_keys),
                }

            error_rate = (errors / total * 100) if total > 0 else 0.0

            # Throughput: runs / elapsed wall-clock seconds
            if self._first_seen is not None and self._last_seen is not None:
                elapsed = self._last_seen - self._first_seen
                throughput = (total / elapsed) if elapsed > 0 else float(total)
            else:
                throughput = 0.0

            # Durations: gaps between consecutive timestamps (ms)
            timestamps = self._durations_ms
            gaps_ms: List[float] = []
            for i in range(1, len(timestamps)):
                gaps_ms.append((timestamps[i] - timestamps[i - 1]) * 1000)

            if gaps_ms:
                avg_ms = statistics.mean(gaps_ms)
                min_ms = min(gaps_ms)
                max_ms = max(gaps_ms)
                sorted_gaps = sorted(gaps_ms)
                p95_idx = max(0, int(len(sorted_gaps) * 0.95) - 1)
                p99_idx = max(0, int(len(sorted_gaps) * 0.99) - 1)
                p95_ms = sorted_gaps[p95_idx]
                p99_ms = sorted_gaps[p99_idx]
            else:
                avg_ms = min_ms = max_ms = p95_ms = p99_ms = 0.0

            return {
                "name": self.name,
                "total_runs": total,
                "error_count": errors,
                "error_rate_pct": round(error_rate, 2),
                "throughput_per_sec": round(throughput, 2),
                "avg_duration_ms": round(avg_ms, 4),
                "min_duration_ms": round(min_ms, 4),
                "max_duration_ms": round(max_ms, 4),
                "p95_duration_ms": round(p95_ms, 4),
                "p99_duration_ms": round(p99_ms, 4),
                "observed_keys": sorted(self._observed_keys),
            }

    def reset(self) -> None:
        """Clear all accumulated data."""
        with self._lock:
            self._total_runs = 0
            self._error_count = 0
            self._durations_ms.clear()
            self._observed_keys.clear()
            self._first_seen = None
            self._last_seen = None

    def export_json(self, path: Optional[str] = None) -> str:
        """Export summary as JSON.  If path given, also write to file."""
        data = self.summary()
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        raw = json.dumps(data, indent=2, default=str)
        if path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(raw, encoding="utf-8")
        return raw


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
