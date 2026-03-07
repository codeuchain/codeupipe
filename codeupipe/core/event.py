"""
Pipeline Events: Structured observable events emitted during execution.

Events follow an OpenTelemetry-compatible shape but require zero dependencies.
Subscribe via Pipeline.on(kind, callback) to observe pipeline behavior.
"""

import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

__all__ = ["PipelineEvent", "EventEmitter"]


@dataclass
class PipelineEvent:
    """A structured event emitted during pipeline execution.

    Kinds:
        - pipeline.start: Pipeline execution begins
        - pipeline.end: Pipeline execution completes
        - step.start: A step begins execution
        - step.end: A step completes execution
        - step.error: A step raises an exception
        - pipeline.retry: A retry attempt begins (from resilience wrapper)
        - circuit.open: Circuit breaker opens (from resilience wrapper)
    """
    kind: str
    step_name: Optional[str] = None
    timestamp: float = field(default_factory=time.monotonic)
    duration: Optional[float] = None
    trace_id: Optional[str] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class EventEmitter:
    """Pub/sub for PipelineEvents. Supports sync and async listeners."""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}

    def on(self, kind: str, callback: Callable) -> None:
        """Subscribe to events of a given kind. Use '*' for all events."""
        self._listeners.setdefault(kind, []).append(callback)

    def off(self, kind: str, callback: Callable) -> None:
        """Unsubscribe a callback from a given event kind."""
        listeners = self._listeners.get(kind, [])
        if callback in listeners:
            listeners.remove(callback)

    async def emit(self, event: PipelineEvent) -> None:
        """Emit an event to all subscribed listeners (sync or async)."""
        for cb in self._listeners.get(event.kind, []):
            result = cb(event)
            if inspect.isawaitable(result):
                await result
        for cb in self._listeners.get("*", []):
            result = cb(event)
            if inspect.isawaitable(result):
                await result
