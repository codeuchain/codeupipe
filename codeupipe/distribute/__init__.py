"""
Distribute: Cross-boundary pipeline execution.

Tools for sending payloads across process and network boundaries,
checkpointing for crash recovery, and source adapters for streaming.
"""

from .remote import RemoteFilter
from .checkpoint import Checkpoint, CheckpointHook
from .source import IterableSource, FileSource
from .worker import WorkerPool

__all__ = [
    "RemoteFilter",
    "Checkpoint", "CheckpointHook",
    "IterableSource", "FileSource",
    "WorkerPool",
]
