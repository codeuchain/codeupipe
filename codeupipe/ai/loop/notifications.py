"""Notification model and queue for hub → agent delivery.

Notification represents a single real-time event from any source
(MCP server, user backchannel, system timer, etc.).

NotificationQueue is a thread-safe, prioritized queue that the hub
writes to and the agent's ReadInputLink drains on each loop iteration.

Both are immutable where possible — Notification is frozen,
NotificationQueue uses internal locking for thread safety since
MCP servers post from different threads/tasks.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum


class NotificationSource(StrEnum):
    """Where a notification originated."""

    USER = "user"
    MCP_SERVER = "mcp_server"
    SYSTEM = "system"
    TIMER = "timer"


class NotificationPriority(IntEnum):
    """Priority levels for notification ordering.

    Lower value = higher priority (processed first).
    """

    URGENT = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass(frozen=True)
class Notification:
    """Immutable notification from any source.

    Attributes:
        source: Where this notification came from.
        source_name: Specific source identifier (e.g. server name, timer name).
        message: Human-readable notification content.
        priority: Ordering priority (urgent → low).
        timestamp: When the notification was created.
        metadata: Optional structured data attached to the notification.
    """

    source: NotificationSource
    source_name: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict | None = None


class NotificationQueue:
    """Thread-safe notification queue for hub → agent delivery.

    The hub (or MCP servers) push notifications from any thread.
    The agent's ReadInputLink drains them on the next loop iteration.

    Notifications are sorted by priority (urgent first), then by
    timestamp (oldest first within same priority).
    """

    def __init__(self) -> None:
        self._queue: list[Notification] = []
        self._lock = threading.Lock()

    def push(self, notification: Notification) -> None:
        """Add a notification to the queue (thread-safe)."""
        with self._lock:
            self._queue.append(notification)

    def drain(self) -> list[Notification]:
        """Remove and return all notifications, sorted by priority then time.

        Returns an empty list if the queue is empty.
        """
        with self._lock:
            if not self._queue:
                return []
            # Sort: priority ascending (urgent=0 first), then timestamp ascending
            sorted_notifs = sorted(
                self._queue,
                key=lambda n: (n.priority, n.timestamp),
            )
            self._queue.clear()
            return sorted_notifs

    def peek(self) -> Notification | None:
        """View the highest-priority notification without removing it."""
        with self._lock:
            if not self._queue:
                return None
            return min(self._queue, key=lambda n: (n.priority, n.timestamp))

    def is_empty(self) -> bool:
        """Check if the queue has any pending notifications."""
        with self._lock:
            return len(self._queue) == 0

    @property
    def size(self) -> int:
        """Number of pending notifications."""
        with self._lock:
            return len(self._queue)
