"""
Payload: The Data Container

The Payload carries data through the pipeline — immutable by default for safety,
mutable when flexibility is needed.
Enhanced with generic typing for type-safe workflows.
"""

import json
from typing import Any, Dict, List, Optional, TypeVar, Generic, Union

__all__ = ["Payload", "MutablePayload"]

T = TypeVar('T')
TInput = TypeVar('TInput')
TOutput = TypeVar('TOutput')


class Payload(Generic[T]):
    """
    Immutable data container — holds data flowing through the pipeline.
    Returns fresh copies on modification for safety.
    Enhanced with generic typing for type-safe workflows.
    """

    def __init__(self, data: Optional[Union[Dict[str, Any], T]] = None, *,
                 trace_id: Optional[str] = None, _lineage: Optional[List[str]] = None):
        if data is None:
            self._data: Dict[str, Any] = {}
        elif isinstance(data, dict):
            self._data = data.copy() if data else {}
        else:
            try:
                self._data = dict(data)  # type: ignore
            except (TypeError, ValueError):
                self._data = {}
        self._trace_id = trace_id
        self._lineage = list(_lineage) if _lineage else []

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for key, or default if absent."""
        return self._data.get(key, default)

    @property
    def trace_id(self) -> Optional[str]:
        """Trace ID for distributed tracing / lineage tracking."""
        return self._trace_id

    @property
    def lineage(self) -> List[str]:
        """Ordered list of step names this payload has passed through."""
        return list(self._lineage)

    def with_trace(self, trace_id: str) -> 'Payload[T]':
        """Return a new Payload with trace ID set."""
        return Payload[T](self._data.copy(), trace_id=trace_id, _lineage=self._lineage)

    def _stamp(self, step_name: str) -> 'Payload[T]':
        """Record a processing step in lineage (internal)."""
        new_lineage = self._lineage + [step_name]
        return Payload[T](self._data.copy(), trace_id=self._trace_id, _lineage=new_lineage)

    def insert(self, key: str, value: Any) -> 'Payload[T]':
        """Return a fresh Payload with the addition."""
        new_data = self._data.copy()
        new_data[key] = value
        return Payload[T](new_data, trace_id=self._trace_id, _lineage=self._lineage)

    def insert_as(self, key: str, value: Any) -> 'Payload[T]':
        """
        Create a new Payload with type evolution — allows clean transformation
        between TypedDict shapes without explicit casting.
        """
        new_data = self._data.copy()
        new_data[key] = value
        return Payload[T](new_data, trace_id=self._trace_id, _lineage=self._lineage)

    def with_mutation(self) -> 'MutablePayload[T]':
        """Convert to a mutable sibling for performance-critical sections."""
        return MutablePayload[T](self._data.copy(), trace_id=self._trace_id, _lineage=self._lineage)

    def merge(self, other: 'Payload[T]') -> 'Payload[T]':
        """Combine payloads, with other taking precedence on conflicts."""
        new_data = self._data.copy()
        new_data.update(other._data)
        trace = self._trace_id or getattr(other, '_trace_id', None)
        lineage = self._lineage + getattr(other, '_lineage', [])
        return Payload[T](new_data, trace_id=trace, _lineage=lineage)

    def to_dict(self) -> Dict[str, Any]:
        """Express as dict for ecosystem integration."""
        return self._data.copy()

    def serialize(self, fmt: str = "json") -> bytes:
        """Serialize payload for network/storage transport."""
        if fmt == "json":
            envelope: Dict[str, Any] = {"data": self._data}
            if self._trace_id:
                envelope["trace_id"] = self._trace_id
            if self._lineage:
                envelope["lineage"] = self._lineage
            return json.dumps(envelope).encode("utf-8")
        raise ValueError(f"Unsupported format: {fmt}")

    @classmethod
    def deserialize(cls, raw: bytes, fmt: str = "json") -> 'Payload':
        """Deserialize payload from network/storage transport."""
        if fmt == "json":
            envelope = json.loads(raw.decode("utf-8"))
            return cls(
                envelope.get("data", {}),
                trace_id=envelope.get("trace_id"),
                _lineage=envelope.get("lineage"),
            )
        raise ValueError(f"Unsupported format: {fmt}")

    def __repr__(self) -> str:
        if self._trace_id:
            return f"Payload({self._data}, trace_id='{self._trace_id}')"
        return f"Payload({self._data})"


class MutablePayload(Generic[T]):
    """
    Mutable data container for performance-critical sections.
    Enhanced with generic typing for type-safe workflows.
    """

    def __init__(self, data: Optional[Dict[str, Any]] = None, *,
                 trace_id: Optional[str] = None, _lineage: Optional[List[str]] = None):
        self._data = data or {}
        self._trace_id = trace_id
        self._lineage = list(_lineage) if _lineage else []

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Change in place."""
        self._data[key] = value

    @property
    def trace_id(self) -> Optional[str]:
        """Trace ID for distributed tracing / lineage tracking."""
        return self._trace_id

    @property
    def lineage(self) -> List[str]:
        """Ordered list of step names this payload has passed through."""
        return list(self._lineage)

    def to_immutable(self) -> Payload[T]:
        """Return to safety with a fresh immutable copy."""
        return Payload[T](self._data.copy(), trace_id=self._trace_id, _lineage=self._lineage)

    def __repr__(self) -> str:
        return f"MutablePayload({self._data})"
