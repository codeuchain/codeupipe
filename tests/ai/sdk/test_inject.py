"""RED PHASE — Tests for Agent.inject() and priority-aware push.

Inject is a request-saving technique: inject a HIGH-priority notification
into the hub's NotificationQueue so it's read by the agent on the next
drain cycle without ending the current turn.

Agent.inject() is the SDK-level convenience; the hub MCP server can also
call HubIOWrapper.post_user_message() directly for the same effect.
"""

import pytest

from codeupipe.ai.loop.notifications import NotificationPriority


class TestAgentInject:
    """Agent.inject() pushes HIGH-priority notifications."""

    def test_inject_pushes_high_priority(self):
        """inject() creates a HIGH-priority notification."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.inject("Focus on security audit")

        notifications = agent._notification_queue.drain()
        assert len(notifications) == 1
        assert notifications[0].message == "Focus on security audit"
        assert notifications[0].priority == NotificationPriority.HIGH

    def test_inject_default_source_is_user(self):
        """inject() defaults source to 'user'."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.inject("Do this next")

        notif = agent._notification_queue.drain()[0]
        assert notif.source_name == "user"

    def test_inject_custom_source(self):
        """inject() accepts a custom source."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.inject("Redeploy", source="ci_server")

        notif = agent._notification_queue.drain()[0]
        assert notif.source_name == "ci_server"

    def test_inject_sorts_before_push(self):
        """inject() (HIGH) sorts before push() (NORMAL) in the queue."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.push("Low priority background task")
        agent.inject("High priority interrupt")

        # Drain returns sorted by priority — HIGH (1) before NORMAL (2)
        notifications = agent._notification_queue.drain()
        assert len(notifications) == 2
        assert notifications[0].message == "High priority interrupt"
        assert notifications[0].priority == NotificationPriority.HIGH
        assert notifications[1].message == "Low priority background task"
        assert notifications[1].priority == NotificationPriority.NORMAL

    def test_inject_urgent_priority(self):
        """inject() can specify URGENT priority."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.inject(
            "Security breach detected",
            priority=NotificationPriority.URGENT,
        )

        notif = agent._notification_queue.drain()[0]
        assert notif.priority == NotificationPriority.URGENT

    def test_multiple_injects_maintain_order(self):
        """Multiple inject() calls maintain timestamp-based order within same priority."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.inject("First")
        agent.inject("Second")
        agent.inject("Third")

        notifications = agent._notification_queue.drain()
        assert len(notifications) == 3
        messages = [n.message for n in notifications]
        assert messages == ["First", "Second", "Third"]

    def test_push_stays_normal_priority(self):
        """push() still uses NORMAL priority (unchanged behavior)."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.push("Background info")

        notif = agent._notification_queue.drain()[0]
        assert notif.priority == NotificationPriority.NORMAL
