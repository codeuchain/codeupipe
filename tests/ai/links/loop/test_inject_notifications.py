"""RED PHASE — Tests for InjectNotificationsLink.

InjectNotificationsLink sits at the front of the turn chain.
It drains the NotificationQueue into pending_notifications
so ReadInputLink can consume them.
"""

from datetime import datetime, timezone

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.inject_notifications import InjectNotificationsLink
from codeupipe.ai.loop.notifications import (
    Notification,
    NotificationPriority,
    NotificationQueue,
    NotificationSource,
)


@pytest.mark.unit
class TestInjectNotificationsLink:
    """Unit tests for InjectNotificationsLink."""

    @pytest.mark.asyncio
    async def test_pass_through_without_queue(self):
        """No notification_queue on context — pass through unchanged."""
        link = InjectNotificationsLink()
        ctx = Payload({"prompt": "hello"})

        result = await link.call(ctx)

        assert result.get("prompt") == "hello"
        assert result.get("pending_notifications") is None

    @pytest.mark.asyncio
    async def test_pass_through_with_non_queue_value(self):
        """notification_queue that isn't a NotificationQueue — pass through."""
        link = InjectNotificationsLink()
        ctx = Payload({"notification_queue": "not-a-queue"})

        result = await link.call(ctx)

        assert result.get("pending_notifications") is None

    @pytest.mark.asyncio
    async def test_pass_through_empty_queue(self):
        """Empty queue — no pending_notifications injected."""
        link = InjectNotificationsLink()
        queue = NotificationQueue()
        ctx = Payload({"notification_queue": queue})

        result = await link.call(ctx)

        assert result.get("pending_notifications") is None

    @pytest.mark.asyncio
    async def test_drains_single_notification(self):
        """Single notification drains into pending_notifications."""
        link = InjectNotificationsLink()
        queue = NotificationQueue()
        queue.push(
            Notification(
                source=NotificationSource.MCP_SERVER,
                source_name="github",
                message="PR approved",
                priority=NotificationPriority.HIGH,
            )
        )
        ctx = Payload({"notification_queue": queue})

        result = await link.call(ctx)

        pending = result.get("pending_notifications")
        assert len(pending) == 1
        assert pending[0]["source"] == "github"
        assert pending[0]["source_type"] == "mcp_server"
        assert pending[0]["message"] == "PR approved"
        assert pending[0]["priority"] == "HIGH"
        assert queue.is_empty() is True

    @pytest.mark.asyncio
    async def test_drains_multiple_ordered_by_priority(self):
        """Multiple notifications come out priority-sorted."""
        link = InjectNotificationsLink()
        queue = NotificationQueue()
        queue.push(
            Notification(
                source=NotificationSource.SYSTEM,
                source_name="timer",
                message="Tick",
                priority=NotificationPriority.LOW,
            )
        )
        queue.push(
            Notification(
                source=NotificationSource.USER,
                source_name="user",
                message="Urgent update",
                priority=NotificationPriority.URGENT,
            )
        )
        ctx = Payload({"notification_queue": queue})

        result = await link.call(ctx)

        pending = result.get("pending_notifications")
        assert len(pending) == 2
        # Urgent first, Low second
        assert pending[0]["message"] == "Urgent update"
        assert pending[1]["message"] == "Tick"

    @pytest.mark.asyncio
    async def test_merges_with_existing_notifications(self):
        """New notifications merge with any already on context."""
        link = InjectNotificationsLink()
        queue = NotificationQueue()
        queue.push(
            Notification(
                source=NotificationSource.SYSTEM,
                source_name="sys",
                message="New event",
            )
        )
        existing = [{"source": "old", "message": "Existing event"}]
        ctx = Payload({
            "notification_queue": queue,
            "pending_notifications": existing,
        })

        result = await link.call(ctx)

        pending = result.get("pending_notifications")
        assert len(pending) == 2
        assert pending[0]["message"] == "Existing event"
        assert pending[1]["message"] == "New event"

    @pytest.mark.asyncio
    async def test_notification_dict_has_all_fields(self):
        """Converted notification dict has all expected keys."""
        link = InjectNotificationsLink()
        ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        queue = NotificationQueue()
        queue.push(
            Notification(
                source=NotificationSource.MCP_SERVER,
                source_name="ci",
                message="Build passed",
                priority=NotificationPriority.NORMAL,
                timestamp=ts,
                metadata={"build_id": 999},
            )
        )
        ctx = Payload({"notification_queue": queue})

        result = await link.call(ctx)

        notif = result.get("pending_notifications")[0]
        assert notif["source"] == "ci"
        assert notif["source_type"] == "mcp_server"
        assert notif["message"] == "Build passed"
        assert notif["priority"] == "NORMAL"
        assert notif["timestamp"] == ts.isoformat()
        assert notif["metadata"] == {"build_id": 999}

    @pytest.mark.asyncio
    async def test_metadata_none_preserved(self):
        """Notification without metadata stores None."""
        link = InjectNotificationsLink()
        queue = NotificationQueue()
        queue.push(
            Notification(
                source=NotificationSource.USER,
                source_name="u",
                message="no meta",
            )
        )
        ctx = Payload({"notification_queue": queue})

        result = await link.call(ctx)

        assert result.get("pending_notifications")[0]["metadata"] is None
