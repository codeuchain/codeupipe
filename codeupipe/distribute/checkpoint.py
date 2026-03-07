"""
Checkpoint: Persist pipeline state for crash recovery and resumption.

Save payload state between pipeline runs or after each step via CheckpointHook.
JSON-based, file system storage. Zero external dependencies.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.payload import Payload
from ..core.hook import Hook

__all__ = ["Checkpoint", "CheckpointHook"]


class Checkpoint:
    """Persist and restore Payload state for crash recovery.

    Usage:
        ckpt = Checkpoint("/tmp/my_pipeline.ckpt")
        ckpt.save(payload, metadata={"step": "transform"})

        # Later, after crash:
        if ckpt.exists:
            payload = ckpt.load()
    """

    def __init__(self, path: str):
        self._path = Path(path)

    def save(self, payload: Payload, *, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Save a payload (with lineage/trace) to disk."""
        data = {
            "payload": payload.to_dict(),
            "trace_id": payload.trace_id,
            "lineage": payload.lineage,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, default=str))

    def load(self) -> Payload:
        """Load a checkpointed payload."""
        raw = json.loads(self._path.read_text())
        return Payload(
            raw["payload"],
            trace_id=raw.get("trace_id"),
            _lineage=raw.get("lineage"),
        )

    @property
    def metadata(self) -> Dict[str, Any]:
        """Retrieve metadata from the last checkpoint."""
        if not self.exists:
            return {}
        raw = json.loads(self._path.read_text())
        return raw.get("metadata", {})

    @property
    def timestamp(self) -> Optional[float]:
        """Retrieve timestamp from the last checkpoint."""
        if not self.exists:
            return None
        raw = json.loads(self._path.read_text())
        return raw.get("timestamp")

    @property
    def exists(self) -> bool:
        """Whether a checkpoint file exists on disk."""
        return self._path.exists()

    def clear(self) -> None:
        """Remove the checkpoint file."""
        if self._path.exists():
            self._path.unlink()


class CheckpointHook(Hook):
    """Hook that automatically checkpoints after each successful step.

    Usage:
        ckpt = Checkpoint("/tmp/pipeline.ckpt")
        pipeline.use_hook(CheckpointHook(ckpt))
    """

    def __init__(self, checkpoint: Checkpoint):
        self._checkpoint = checkpoint
        self._step_count = 0

    async def after(self, filter, payload) -> None:
        if filter is not None:
            self._step_count += 1
            self._checkpoint.save(payload, metadata={"step": self._step_count})
