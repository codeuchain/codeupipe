"""RED PHASE — Tests for BackchannelLink.

BackchannelLink extracts __notifications__ from tool results
and pushes them to the NotificationQueue so they appear in the
agent's next READ cycle via InjectNotificationsLink.
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.backchannel import BackchannelLink, BACKCHANNEL_KEY
from codeupipe.ai.loop.notifications import (
    NotificationPriority,
    NotificationQueue,
    NotificationSource,
)


@pytest.mark.unit
class TestBackchannelLink:
    """Unit tests for BackchannelLink."""

    @pytest.mark.asyncio
    async def test_pass_through_no_queue(self):
        """No notification_queue — pass through unchanged."""
        link = BackchannelLink()
        ctx = Payload({"last_response_event": {"result": {}}})

        result = await link.call(ctx)
        assert result.get("last_response_event") is not None

    @pytest.mark.asyncio
    async def test_pass_through_no_event(self):
        """No last_response_event — pass through."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({"notification_queue": queue})

        result = await link.call(ctx)
        assert queue.is_empty() is True

    @pytest.mark.asyncio
    async def test_pass_through_no_notifications_in_result(self):
        """Tool result without __notifications__ — nothing pushed."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {"result": {"output": "clean data"}},
        })

        result = await link.call(ctx)
        assert queue.is_empty() is True

    @pytest.mark.asyncio
    async def test_extracts_single_notification(self):
        """Single backchannel notification is pushed to queue."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {
                "result": {
                    "output": "done",
                    BACKCHANNEL_KEY: [
                        {
                            "source": "ci_server",
                            "message": "Build passed",
                            "priority": "HIGH",
                        }
                    ],
                },
            },
        })

        await link.call(ctx)

        assert queue.size == 1
        notif = queue.drain()[0]
        assert notif.source == NotificationSource.MCP_SERVER
        assert notif.source_name == "ci_server"
        assert notif.message == "Build passed"
        assert notif.priority == NotificationPriority.HIGH

    @pytest.mark.asyncio
    async def test_extracts_multiple_notifications(self):
        """Multiple backchannel notifications are all pushed."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {
                "result": {
                    BACKCHANNEL_KEY: [
                        {"source": "a", "message": "msg1"},
                        {"source": "b", "message": "msg2"},
                    ],
                },
            },
        })

        await link.call(ctx)

        assert queue.size == 2
        messages = [n.message for n in queue.drain()]
        assert "msg1" in messages
        assert "msg2" in messages

    @pytest.mark.asyncio
    async def test_default_priority_is_normal(self):
        """Missing priority defaults to NORMAL."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {
                "result": {
                    BACKCHANNEL_KEY: [
                        {"source": "s", "message": "no priority"},
                    ],
                },
            },
        })

        await link.call(ctx)

        notif = queue.drain()[0]
        assert notif.priority == NotificationPriority.NORMAL

    @pytest.mark.asyncio
    async def test_invalid_priority_falls_back(self):
        """Unknown priority string falls back to NORMAL."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {
                "result": {
                    BACKCHANNEL_KEY: [
                        {"source": "s", "message": "bad", "priority": "INVALID"},
                    ],
                },
            },
        })

        await link.call(ctx)

        notif = queue.drain()[0]
        assert notif.priority == NotificationPriority.NORMAL

    @pytest.mark.asyncio
    async def test_skips_entries_without_message(self):
        """Entries missing 'message' are skipped."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {
                "result": {
                    BACKCHANNEL_KEY: [
                        {"source": "s"},  # no message
                        {"source": "s", "message": "valid"},
                    ],
                },
            },
        })

        await link.call(ctx)

        assert queue.size == 1
        assert queue.drain()[0].message == "valid"

    @pytest.mark.asyncio
    async def test_skips_non_dict_entries(self):
        """Non-dict entries in __notifications__ are skipped."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {
                "result": {
                    BACKCHANNEL_KEY: [
                        "not a dict",
                        42,
                        {"source": "s", "message": "valid"},
                    ],
                },
            },
        })

        await link.call(ctx)

        assert queue.size == 1

    @pytest.mark.asyncio
    async def test_single_notification_not_in_list(self):
        """Single notification dict (not wrapped in list) still works."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {
                "result": {
                    BACKCHANNEL_KEY: {
                        "source": "solo",
                        "message": "single item",
                    },
                },
            },
        })

        await link.call(ctx)

        assert queue.size == 1
        assert queue.drain()[0].message == "single item"

    @pytest.mark.asyncio
    async def test_metadata_passed_through(self):
        """Metadata from backchannel notification is preserved."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {
                "result": {
                    BACKCHANNEL_KEY: [
                        {
                            "source": "s",
                            "message": "with meta",
                            "metadata": {"key": "value"},
                        },
                    ],
                },
            },
        })

        await link.call(ctx)

        notif = queue.drain()[0]
        assert notif.metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_source_defaults_to_unknown(self):
        """Missing source defaults to 'unknown_server'."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {
                "result": {
                    BACKCHANNEL_KEY: [
                        {"message": "no source field"},
                    ],
                },
            },
        })

        await link.call(ctx)

        notif = queue.drain()[0]
        assert notif.source_name == "unknown_server"

    @pytest.mark.asyncio
    async def test_handles_session_event_like_object(self):
        """Handles event with .data attribute (SessionEvent-like)."""
        link = BackchannelLink()
        queue = NotificationQueue()

        class MockEvent:
            data = {
                "result": {
                    BACKCHANNEL_KEY: [
                        {"source": "mock", "message": "via data attr"},
                    ],
                },
            }

        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": MockEvent(),
        })

        await link.call(ctx)

        assert queue.size == 1
        assert queue.drain()[0].message == "via data attr"

    @pytest.mark.asyncio
    async def test_handles_tool_results_list(self):
        """Handles event with tool_results list."""
        link = BackchannelLink()
        queue = NotificationQueue()
        ctx = Payload({
            "notification_queue": queue,
            "last_response_event": {
                "tool_results": [
                    {
                        BACKCHANNEL_KEY: [
                            {"source": "a", "message": "from list"},
                        ],
                    },
                    {
                        "output": "no notifications here",
                    },
                ],
            },
        })

        await link.call(ctx)

        assert queue.size == 1
        assert queue.drain()[0].message == "from list"
