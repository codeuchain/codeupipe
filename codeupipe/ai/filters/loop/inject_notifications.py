"""InjectNotificationsLink — Drain the notification queue into context.

Sits between ReadInputLink and LanguageModelLink in the turn chain.
On each iteration, drains the NotificationQueue and formats
notifications as pending_notifications on context for ReadInputLink
to consume on the next iteration (or this one if it's a follow-up).

If no NotificationQueue is on context, passes through unchanged
(backward compatible with single-turn usage).

Input:  notification_queue (NotificationQueue, optional)
Output: pending_notifications (list[dict])
"""

from codeupipe import Payload

from codeupipe.ai.loop.notifications import NotificationQueue


class InjectNotificationsLink:
    """Drain notification queue and inject into context."""

    async def call(self, payload: Payload) -> Payload:
        queue = payload.get("notification_queue")
        if not isinstance(queue, NotificationQueue):
            # No queue — backward compatible pass-through
            return payload

        if queue.is_empty():
            return payload

        # Drain all pending notifications
        notifications = queue.drain()

        # Convert to dicts for context storage (Context is immutable,
        # so we store plain dicts that ReadInputLink can format)
        pending = [
            {
                "source": notif.source_name,
                "source_type": str(notif.source),
                "message": notif.message,
                "priority": str(notif.priority.name),
                "timestamp": notif.timestamp.isoformat(),
                "metadata": notif.metadata,
            }
            for notif in notifications
        ]

        # Merge with any existing pending notifications
        existing = payload.get("pending_notifications") or []
        merged = existing + pending

        return payload.insert("pending_notifications", merged)
