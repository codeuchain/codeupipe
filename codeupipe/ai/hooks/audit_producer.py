"""AuditProducer — Abstract interface + concrete sinks for audit events.

Fire-and-forget async producers that ship AuditEvents to external
systems.  The agent never blocks on audit delivery.

Sinks:
  - LogAuditSink — writes to Python logging (development/debugging)
  - FileAuditSink — appends JSON lines to a file (local capture)
  - NoopAuditSink — discards events (testing/disabled audit)

For production, implement KafkaAuditSink, SQSAuditSink, etc. by
extending AuditProducer with the appropriate async client.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from codeupipe.ai.hooks.audit_event import AuditEvent

logger = logging.getLogger("codeupipe.ai.hooks.audit")


class AuditProducer(ABC):
    """Abstract base for audit event producers.

    Implementations should be async-safe and fire-and-forget.
    If delivery fails, log and move on — never block the agent.
    """

    @abstractmethod
    async def send(self, event: AuditEvent) -> None:
        """Ship a single audit event.  Must not raise."""

    async def flush(self) -> None:
        """Flush pending events (optional for batching producers)."""

    async def close(self) -> None:
        """Clean up resources (optional)."""


class LogAuditSink(AuditProducer):
    """Write audit events to Python logging.

    Good for development, debugging, and local visibility.
    """

    def __init__(self, level: int = logging.DEBUG) -> None:
        self._level = level

    async def send(self, event: AuditEvent) -> None:
        try:
            logger.log(
                self._level,
                "📋 [%s] iter=%d duration=%.1fms keys=%s→%s%s",
                event.link_name,
                event.loop_iteration,
                event.duration_ms,
                list(event.input_keys),
                list(event.output_keys),
                f" error={event.error}" if event.error else "",
            )
        except Exception:  # noqa: BLE001
            pass  # fire and forget


class FileAuditSink(AuditProducer):
    """Append audit events as JSON lines to a file.

    Good for local capture and later batch processing.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def send(self, event: AuditEvent) -> None:
        try:
            line = json.dumps(event.to_dict(), default=str) + "\n"
            with self._path.open("a") as f:
                f.write(line)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to write audit event to %s", self._path)


class NoopAuditSink(AuditProducer):
    """Discard audit events — for testing or disabled audit."""

    async def send(self, event: AuditEvent) -> None:
        pass


class CompositeAuditProducer(AuditProducer):
    """Fan-out to multiple sinks.

    E.g. log locally AND ship to Kafka simultaneously.
    """

    def __init__(self, sinks: list[AuditProducer]) -> None:
        self._sinks = sinks

    async def send(self, event: AuditEvent) -> None:
        for sink in self._sinks:
            try:
                await sink.send(event)
            except Exception:  # noqa: BLE001
                logger.warning("Audit sink %s failed", type(sink).__name__)

    async def flush(self) -> None:
        for sink in self._sinks:
            await sink.flush()

    async def close(self) -> None:
        for sink in self._sinks:
            await sink.close()
