"""
Core Module: Base Protocols and Classes

The foundation — protocols, abstract base classes, and fundamental types.
"""

from .payload import Payload, MutablePayload
from .filter import Filter
from .stream_filter import StreamFilter
from .pipeline import Pipeline, CircuitOpenError
from .valve import Valve
from .tap import Tap
from .state import State
from .hook import Hook
from .event import PipelineEvent, EventEmitter
from .govern import (
    PayloadSchema, SchemaViolation, ContractViolation, PipelineTimeoutError,
    AuditEntry, AuditTrail, AuditHook,
    DeadLetterHandler, LogDeadLetterHandler,
)
from .secure import (
    seal_payload, verify_payload, encrypt_data, decrypt_data,
    SecurePayloadError,
)
from .sign_filter import SignFilter
from .verify_filter import VerifyFilter
from .encrypt_filter import EncryptFilter
from .decrypt_filter import DecryptFilter

__all__ = [
    "Payload", "MutablePayload",
    "Filter", "StreamFilter", "Pipeline", "CircuitOpenError", "Valve", "Tap",
    "State", "Hook",
    "PipelineEvent", "EventEmitter",
    # Govern
    "PayloadSchema", "SchemaViolation", "ContractViolation", "PipelineTimeoutError",
    "AuditEntry", "AuditTrail", "AuditHook",
    "DeadLetterHandler", "LogDeadLetterHandler",
    # Secure
    "SignFilter", "VerifyFilter", "EncryptFilter", "DecryptFilter",
    "seal_payload", "verify_payload", "encrypt_data", "decrypt_data",
    "SecurePayloadError",
]