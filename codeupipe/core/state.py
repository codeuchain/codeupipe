"""
State: Pipeline Execution Metadata

State tracks what happened during pipeline execution — which filters ran,
which were skipped, timing data, and errors encountered.
Access it after pipeline.run() via pipeline.state.
"""

from typing import Any, Dict, List, Optional, Tuple, Set

__all__ = ["State"]


class State:
    """
    Pipeline execution state — tracks filter execution, timing, and errors.

    Provides visibility into what happened during a pipeline run:
    - Which filters executed and in what order
    - Which filters were skipped (by valves)
    - Errors encountered during execution
    - Arbitrary metadata for custom tracking
    """

    def __init__(self):
        self.executed: List[str] = []
        self.skipped: List[str] = []
        self.errors: List[Tuple[str, Exception]] = []
        self.metadata: Dict[str, Any] = {}
        self.chunks_processed: Dict[str, int] = {}
        self.timings: Dict[str, float] = {}

    def mark_executed(self, name: str) -> None:
        """Record that a filter executed."""
        self.executed.append(name)

    def mark_skipped(self, name: str) -> None:
        """Record that a filter was skipped."""
        self.skipped.append(name)

    def increment_chunks(self, name: str, count: int = 1) -> None:
        """Increment the chunk counter for a streaming step."""
        self.chunks_processed[name] = self.chunks_processed.get(name, 0) + count

    def record_timing(self, name: str, duration: float) -> None:
        """Record step execution duration in seconds."""
        self.timings[name] = duration

    def record_error(self, name: str, error: Exception) -> None:
        """Record an error from a filter."""
        self.errors.append((name, error))

    def set(self, key: str, value: Any) -> None:
        """Store arbitrary metadata."""
        self.metadata[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve metadata."""
        return self.metadata.get(key, default)

    @property
    def has_errors(self) -> bool:
        """Whether any errors were recorded."""
        return len(self.errors) > 0

    @property
    def last_error(self) -> Optional[Exception]:
        """The most recent error, or None."""
        return self.errors[-1][1] if self.errors else None

    def reset(self) -> None:
        """Reset state for a fresh run."""
        self.executed.clear()
        self.skipped.clear()
        self.errors.clear()
        self.metadata.clear()
        self.chunks_processed.clear()
        self.timings.clear()

    def diff(self, other: 'State') -> Dict[str, Any]:
        """Compare this state with another — what changed between runs."""
        result: Dict[str, Any] = {}

        added = [s for s in other.executed if s not in self.executed]
        removed = [s for s in self.executed if s not in other.executed]
        if added:
            result["added_steps"] = added
        if removed:
            result["removed_steps"] = removed

        timing_changes: Dict[str, Dict[str, Optional[float]]] = {}
        all_steps: Set[str] = set(self.timings) | set(other.timings)
        for step in sorted(all_steps):
            old_t = self.timings.get(step)
            new_t = other.timings.get(step)
            if old_t != new_t:
                timing_changes[step] = {"old": old_t, "new": new_t}
        if timing_changes:
            result["timing_changes"] = timing_changes

        old_errors: Set[str] = {name for name, _ in self.errors}
        new_errors: Set[str] = {name for name, _ in other.errors}
        if old_errors != new_errors:
            result["error_changes"] = {
                "added": sorted(new_errors - old_errors),
                "removed": sorted(old_errors - new_errors),
            }

        return result

    def __repr__(self) -> str:
        return (
            f"State(executed={self.executed}, skipped={self.skipped}, "
            f"errors={len(self.errors)}, timings={len(self.timings)}, "
            f"chunks={self.chunks_processed})"
        )