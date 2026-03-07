"""
Govern: Pipeline-level guarantees — shape, time, rate, and failure policy.

Ring 6 of the codeupipe expansion. Provides:
- PayloadSchema — shape validation on Payload data
- Contract violations — clear, typed exceptions for pre/post conditions
- Timeout policies — per-pipeline clean cancellation
- Rate limiting — token-bucket throttling for external API protection
- Dead letter handling — route failed payloads instead of losing them
- Audit trail — immutable log of every payload transformation
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from .hook import Hook
from .payload import Payload

__all__ = [
    "PayloadSchema",
    "SchemaViolation",
    "ContractViolation",
    "PipelineTimeoutError",
    "AuditEntry",
    "AuditTrail",
    "AuditHook",
    "DeadLetterHandler",
    "LogDeadLetterHandler",
]


# ──────────────────────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────────────────────

class SchemaViolation(Exception):
    """Raised when a Payload fails schema validation."""


class ContractViolation(Exception):
    """Raised when a pipeline pre/post contract is violated."""


class PipelineTimeoutError(Exception):
    """Raised when a pipeline exceeds its configured timeout."""


# ──────────────────────────────────────────────────────────────
# Payload Schema
# ──────────────────────────────────────────────────────────────

class PayloadSchema:
    """Optional shape validation for Payload data.

    Validates that a Payload contains the expected keys and (optionally) types.

    Usage:
        schema = PayloadSchema({"user_id": int, "email": str})
        schema.validate(payload)  # raises SchemaViolation if invalid

        # Keys-only (no type checking):
        schema = PayloadSchema.keys("user_id", "email")
        schema.validate(payload)
    """

    def __init__(self, shape: Dict[str, type]):
        self._shape = dict(shape)

    @classmethod
    def keys(cls, *keys: str) -> "PayloadSchema":
        """Create a schema that only checks key presence, not types."""
        return cls({k: object for k in keys})

    def validate(self, payload: Payload) -> None:
        """Validate a Payload against this schema. Raises SchemaViolation on failure."""
        data = payload.to_dict()
        missing = []
        type_errors = []

        for key, expected_type in self._shape.items():
            if key not in data:
                missing.append(key)
            elif expected_type is not object and not isinstance(data[key], expected_type):
                type_errors.append(
                    f"'{key}': expected {expected_type.__name__}, "
                    f"got {type(data[key]).__name__}"
                )

        errors = []
        if missing:
            errors.append(f"Missing keys: {', '.join(missing)}")
        if type_errors:
            errors.append(f"Type errors: {'; '.join(type_errors)}")

        if errors:
            raise SchemaViolation(" | ".join(errors))

    @property
    def required_keys(self) -> Set[str]:
        """The set of keys this schema requires."""
        return set(self._shape.keys())

    def __repr__(self) -> str:
        parts = []
        for k, v in self._shape.items():
            parts.append(f"{k}: {v.__name__}" if v is not object else k)
        return f"PayloadSchema({{{', '.join(parts)}}})"


# ──────────────────────────────────────────────────────────────
# Audit Trail
# ──────────────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    """A single immutable record in the audit trail."""
    step_name: str
    timestamp: float
    input_keys: List[str]
    output_keys: List[str]
    phase: str  # "before" or "after"
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuditTrail:
    """Immutable append-only log of pipeline transformations.

    Entries are recorded by the AuditHook during pipeline execution.
    Access via audit_trail.entries after pipeline.run().
    """

    def __init__(self):
        self._entries: List[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        """Append an entry to the audit trail."""
        self._entries.append(entry)

    @property
    def entries(self) -> List[AuditEntry]:
        """Return a copy of the audit entries."""
        return list(self._entries)

    @property
    def step_names(self) -> List[str]:
        """Ordered list of step names that ran (after-phase only)."""
        return [e.step_name for e in self._entries if e.phase == "after"]

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"AuditTrail({len(self._entries)} entries)"


class AuditHook(Hook):
    """Lifecycle hook that records every payload transformation into an AuditTrail.

    Usage:
        trail = AuditTrail()
        hook = AuditHook(trail)
        pipeline.use_hook(hook)
        await pipeline.run(payload)
        print(trail.entries)
    """

    def __init__(self, trail: AuditTrail):
        self._trail = trail
        self._snapshots: Dict[int, List[str]] = {}

    @property
    def trail(self) -> AuditTrail:
        return self._trail

    async def before(self, filter, payload) -> None:
        if filter is not None:
            self._snapshots[id(filter)] = list(payload.to_dict().keys())

    async def after(self, filter, payload) -> None:
        if filter is not None:
            input_keys = self._snapshots.pop(id(filter), [])
            output_keys = list(payload.to_dict().keys())
            self._trail.record(AuditEntry(
                step_name=filter.__class__.__name__,
                timestamp=time.monotonic(),
                input_keys=input_keys,
                output_keys=output_keys,
                phase="after",
            ))

    async def on_error(self, filter, error, payload) -> None:
        if filter is not None:
            input_keys = self._snapshots.pop(id(filter), [])
            step_name = filter.__class__.__name__
        else:
            input_keys = []
            step_name = "pipeline"
        self._trail.record(AuditEntry(
            step_name=step_name,
            timestamp=time.monotonic(),
            input_keys=input_keys,
            output_keys=list(payload.to_dict().keys()),
            phase="error",
            metadata={"error": str(error)},
        ))


# ──────────────────────────────────────────────────────────────
# Dead Letter Handler Protocol
# ──────────────────────────────────────────────────────────────

class DeadLetterHandler(ABC):
    """Protocol for handling failed payloads that would otherwise be lost."""

    @abstractmethod
    async def handle(self, payload: Payload, error: Exception) -> None:
        """Process a dead letter payload. Must not raise."""


class LogDeadLetterHandler(DeadLetterHandler):
    """Collects dead letters into an in-memory list for inspection.

    Usage:
        dlh = LogDeadLetterHandler()
        pipeline.with_dead_letter(dlh)
        ...
        print(dlh.dead_letters)  # list of (payload, error) tuples
    """

    def __init__(self):
        self._dead_letters: List[tuple] = []

    async def handle(self, payload: Payload, error: Exception) -> None:
        self._dead_letters.append((payload, error))

    @property
    def dead_letters(self) -> List[tuple]:
        """List of (payload, error) tuples."""
        return list(self._dead_letters)

    def __len__(self) -> int:
        return len(self._dead_letters)
