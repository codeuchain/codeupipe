"""BackchannelLink — Extract backchannel notifications from tool results.

The lifecycle doc says: "Lower-tier MCP servers don't talk to the
agent directly. They talk to the hub. The hub decides when and how
to relay that information."

This link runs after ProcessResponseLink.  It inspects the last
response event for tool results that contain backchannel markers
(a convention where tools embed notifications in their output).

If a tool result includes a `__notifications__` key, those are
extracted, converted to Notifications, and pushed to the
NotificationQueue.  They'll appear in the agent's next READ cycle
via InjectNotificationsLink.

This is the mechanism by which MCP servers "talk to the hub"
within the Copilot SDK's tool-execution model.

Input:  last_response_event (dict|None), notification_queue (NotificationQueue)
Output: context unchanged (notifications are pushed to the queue)
"""

import logging

from codeupipe import Payload

from codeupipe.ai.loop.notifications import (
    NotificationPriority,
    NotificationQueue,
    NotificationSource,
    Notification,
)

logger = logging.getLogger("codeupipe.ai.loop")

# Convention: tools embed this key in results to post backchannel
BACKCHANNEL_KEY = "__notifications__"


class BackchannelLink:
    """Extract backchannel notifications from tool execution results."""

    async def call(self, payload: Payload) -> Payload:
        queue = payload.get("notification_queue")
        if not isinstance(queue, NotificationQueue):
            # No queue — can't deliver backchannel messages
            return payload

        event = payload.get("last_response_event")
        if event is None:
            return payload

        # Extract tool results from the response event
        # The SessionEvent.data can contain tool results in several forms
        tool_results = self._extract_tool_results(event)

        for result in tool_results:
            notifications = self._extract_notifications(result)
            for notif in notifications:
                queue.push(notif)
                logger.info(
                    "Backchannel notification from %s: %s",
                    notif.source_name,
                    notif.message[:80],
                )

        return payload

    def _extract_tool_results(self, event: object) -> list[dict]:
        """Pull tool result dicts from a response event."""
        results: list[dict] = []

        if isinstance(event, dict):
            # Direct dict with tool_result
            if "result" in event and isinstance(event["result"], dict):
                results.append(event["result"])
            # List of tool results
            if "tool_results" in event:
                for r in event["tool_results"]:
                    if isinstance(r, dict):
                        results.append(r)
        elif hasattr(event, "data"):
            # SessionEvent-like object
            data = event.data
            if isinstance(data, dict):
                if "result" in data and isinstance(data["result"], dict):
                    results.append(data["result"])
                if "tool_results" in data:
                    for r in data["tool_results"]:
                        if isinstance(r, dict):
                            results.append(r)
            elif data is not None:
                # Dataclass or object with attributes
                if hasattr(data, "tool_results") and data.tool_results:
                    for r in data.tool_results:
                        if isinstance(r, dict):
                            results.append(r)

        return results

    def _extract_notifications(self, result: dict) -> list[Notification]:
        """Extract backchannel notifications from a single tool result."""
        raw = result.get(BACKCHANNEL_KEY)
        if not raw:
            return []

        if not isinstance(raw, list):
            raw = [raw]

        notifications: list[Notification] = []
        for item in raw:
            if not isinstance(item, dict):
                continue

            message = item.get("message", "")
            if not message:
                continue

            source_name = item.get("source", "unknown_server")
            priority_str = item.get("priority", "NORMAL").upper()

            try:
                priority = NotificationPriority[priority_str]
            except KeyError:
                priority = NotificationPriority.NORMAL

            notifications.append(
                Notification(
                    source=NotificationSource.MCP_SERVER,
                    source_name=source_name,
                    message=message,
                    priority=priority,
                    metadata=item.get("metadata"),
                )
            )

        return notifications
