"""RED PHASE — Tests for Notification, NotificationQueue, and enums.

NotificationQueue is the hub → agent delivery mechanism.
Thread-safe, priority-sorted, drain-based consumption.
"""

import threading
from datetime import datetime, timezone

import pytest

from codeupipe.ai.loop.notifications import (
    Notification,
    NotificationPriority,
    NotificationQueue,
    NotificationSource,
)


@pytest.mark.unit
class TestNotificationSource:
    """Unit tests for NotificationSource enum."""

    def test_values(self):
        """All expected source types exist."""
        assert NotificationSource.USER == "user"
        assert NotificationSource.MCP_SERVER == "mcp_server"
        assert NotificationSource.SYSTEM == "system"
        assert NotificationSource.TIMER == "timer"


@pytest.mark.unit
class TestNotificationPriority:
    """Unit tests for NotificationPriority enum."""

    def test_ordering(self):
        """Urgent < High < Normal < Low (lower = higher priority)."""
        assert NotificationPriority.URGENT < NotificationPriority.HIGH
        assert NotificationPriority.HIGH < NotificationPriority.NORMAL
        assert NotificationPriority.NORMAL < NotificationPriority.LOW

    def test_values(self):
        """Priority levels have expected integer values."""
        assert NotificationPriority.URGENT == 0
        assert NotificationPriority.HIGH == 1
        assert NotificationPriority.NORMAL == 2
        assert NotificationPriority.LOW == 3


@pytest.mark.unit
class TestNotification:
    """Unit tests for Notification (frozen dataclass)."""

    def test_create_with_defaults(self):
        """Notification can be created with minimal args."""
        notif = Notification(
            source=NotificationSource.SYSTEM,
            source_name="health_check",
            message="All systems go",
        )
        assert notif.source == NotificationSource.SYSTEM
        assert notif.source_name == "health_check"
        assert notif.message == "All systems go"
        assert notif.priority == NotificationPriority.NORMAL
        assert isinstance(notif.timestamp, datetime)
        assert notif.metadata is None

    def test_create_with_all_fields(self):
        """Notification stores all explicit field values."""
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        notif = Notification(
            source=NotificationSource.MCP_SERVER,
            source_name="github",
            message="PR merged",
            priority=NotificationPriority.HIGH,
            timestamp=ts,
            metadata={"pr_number": 42},
        )
        assert notif.source == NotificationSource.MCP_SERVER
        assert notif.source_name == "github"
        assert notif.priority == NotificationPriority.HIGH
        assert notif.timestamp == ts
        assert notif.metadata == {"pr_number": 42}

    def test_is_frozen(self):
        """Notification is immutable."""
        notif = Notification(
            source=NotificationSource.USER,
            source_name="user_1",
            message="hello",
        )
        with pytest.raises(AttributeError):
            notif.message = "changed"  # type: ignore


@pytest.mark.unit
class TestNotificationQueue:
    """Unit tests for NotificationQueue (thread-safe, priority-sorted)."""

    def _make_notif(
        self,
        message: str = "test",
        priority: NotificationPriority = NotificationPriority.NORMAL,
        source: NotificationSource = NotificationSource.SYSTEM,
        source_name: str = "test",
        timestamp: datetime | None = None,
    ) -> Notification:
        """Helper to create a Notification with minimal boilerplate."""
        kwargs: dict = {
            "source": source,
            "source_name": source_name,
            "message": message,
            "priority": priority,
        }
        if timestamp is not None:
            kwargs["timestamp"] = timestamp
        return Notification(**kwargs)

    def test_starts_empty(self):
        """Queue starts with no notifications."""
        q = NotificationQueue()
        assert q.is_empty() is True
        assert q.size == 0

    def test_push_and_size(self):
        """Push increases size."""
        q = NotificationQueue()
        q.push(self._make_notif("a"))
        assert q.size == 1
        assert q.is_empty() is False
        q.push(self._make_notif("b"))
        assert q.size == 2

    def test_drain_returns_all(self):
        """Drain returns all notifications and empties the queue."""
        q = NotificationQueue()
        q.push(self._make_notif("a"))
        q.push(self._make_notif("b"))

        result = q.drain()
        assert len(result) == 2
        assert q.is_empty() is True
        assert q.size == 0

    def test_drain_empty_returns_empty_list(self):
        """Draining an empty queue returns an empty list."""
        q = NotificationQueue()
        assert q.drain() == []

    def test_drain_sorts_by_priority(self):
        """Drain returns urgent before low priority."""
        q = NotificationQueue()
        q.push(self._make_notif("low", NotificationPriority.LOW))
        q.push(self._make_notif("urgent", NotificationPriority.URGENT))
        q.push(self._make_notif("normal", NotificationPriority.NORMAL))

        result = q.drain()
        messages = [n.message for n in result]
        assert messages == ["urgent", "normal", "low"]

    def test_drain_sorts_by_timestamp_within_priority(self):
        """Same-priority notifications are sorted oldest first."""
        q = NotificationQueue()
        t1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
        t3 = datetime(2025, 1, 1, 12, 0, 2, tzinfo=timezone.utc)

        q.push(self._make_notif("c", timestamp=t3))
        q.push(self._make_notif("a", timestamp=t1))
        q.push(self._make_notif("b", timestamp=t2))

        result = q.drain()
        messages = [n.message for n in result]
        assert messages == ["a", "b", "c"]

    def test_peek_returns_highest_priority(self):
        """Peek shows highest-priority notification without removing."""
        q = NotificationQueue()
        q.push(self._make_notif("low", NotificationPriority.LOW))
        q.push(self._make_notif("urgent", NotificationPriority.URGENT))

        peeked = q.peek()
        assert peeked is not None
        assert peeked.message == "urgent"
        assert q.size == 2  # not removed

    def test_peek_empty_returns_none(self):
        """Peek on empty queue returns None."""
        q = NotificationQueue()
        assert q.peek() is None

    def test_thread_safety(self):
        """Multiple threads can push concurrently without corruption."""
        q = NotificationQueue()
        count_per_thread = 100
        num_threads = 10
        barrier = threading.Barrier(num_threads)

        def pusher(thread_id: int) -> None:
            barrier.wait()  # synchronize start
            for i in range(count_per_thread):
                q.push(self._make_notif(f"t{thread_id}-{i}"))

        threads = [
            threading.Thread(target=pusher, args=(t,))
            for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert q.size == num_threads * count_per_thread
        drained = q.drain()
        assert len(drained) == num_threads * count_per_thread
        assert q.is_empty() is True

    def test_drain_is_idempotent(self):
        """Second drain after first returns empty."""
        q = NotificationQueue()
        q.push(self._make_notif("once"))

        first = q.drain()
        assert len(first) == 1
        second = q.drain()
        assert second == []
