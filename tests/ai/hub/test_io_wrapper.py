"""RED PHASE — Tests for HubIOWrapper.

HubIOWrapper is the coordinator that owns the notification queue,
server registry, and context budget.  It provides seed_context()
for injection, build_context() for centralised context assembly,
and convenience methods for backchannel posting.
"""

import pytest

from codeupipe.ai.hub.config import ServerConfig
from codeupipe.ai.hub.io_wrapper import HubIOWrapper
from codeupipe.ai.hub.registry import ServerRegistry
from codeupipe.ai.loop.context_schema import ContextEntry, Zone
from codeupipe.ai.loop.notifications import (
    NotificationPriority,
    NotificationSource,
)


@pytest.mark.unit
class TestHubIOWrapper:
    """Unit tests for HubIOWrapper."""

    def _make_wrapper(self, **kwargs) -> HubIOWrapper:
        """Create a wrapper with an empty registry."""
        registry = kwargs.pop("server_registry", ServerRegistry())
        return HubIOWrapper(server_registry=registry, **kwargs)

    def test_default_budget(self):
        """Default context budget is 128k tokens."""
        wrapper = self._make_wrapper()
        assert wrapper.context_budget == 128_000

    def test_custom_budget(self):
        """Context budget can be set at creation."""
        wrapper = self._make_wrapper(context_budget=64_000)
        assert wrapper.context_budget == 64_000

    def test_notification_queue_auto_created(self):
        """NotificationQueue is created automatically."""
        wrapper = self._make_wrapper()
        assert wrapper.notification_queue.is_empty() is True

    def test_server_registry_stored(self):
        """Server registry is accessible."""
        registry = ServerRegistry()
        registry.register(ServerConfig(name="test", command="echo"))
        wrapper = self._make_wrapper(server_registry=registry)
        assert wrapper.server_registry.has("test")

    # ── seed_context ──────────────────────────────────────────────────

    def test_seed_context_returns_required_keys(self):
        """seed_context produces notification_queue, context_budget, hub_io."""
        wrapper = self._make_wrapper()
        ctx = wrapper.seed_context()

        assert "notification_queue" in ctx
        assert "context_budget" in ctx
        assert "hub_io" in ctx
        assert ctx["hub_io"] is wrapper
        assert ctx["notification_queue"] is wrapper.notification_queue
        assert ctx["context_budget"] == 128_000

    # ── post_notification ─────────────────────────────────────────────

    def test_post_notification_pushes_to_queue(self):
        """post_notification adds to the notification queue."""
        wrapper = self._make_wrapper()
        wrapper.post_notification(
            source=NotificationSource.SYSTEM,
            source_name="health",
            message="All good",
        )
        assert wrapper.notification_queue.size == 1
        notif = wrapper.notification_queue.drain()[0]
        assert notif.source == NotificationSource.SYSTEM
        assert notif.source_name == "health"
        assert notif.message == "All good"
        assert notif.priority == NotificationPriority.NORMAL

    def test_post_notification_with_priority(self):
        """post_notification respects priority kwarg."""
        wrapper = self._make_wrapper()
        wrapper.post_notification(
            source=NotificationSource.USER,
            source_name="user",
            message="Urgent!",
            priority=NotificationPriority.URGENT,
        )
        notif = wrapper.notification_queue.drain()[0]
        assert notif.priority == NotificationPriority.URGENT

    def test_post_notification_with_metadata(self):
        """post_notification passes metadata through."""
        wrapper = self._make_wrapper()
        wrapper.post_notification(
            source=NotificationSource.MCP_SERVER,
            source_name="ci",
            message="Build done",
            metadata={"build_id": 42},
        )
        notif = wrapper.notification_queue.drain()[0]
        assert notif.metadata == {"build_id": 42}

    # ── Shorthand methods ─────────────────────────────────────────────

    def test_post_tool_notification(self):
        """post_tool_notification uses MCP_SERVER source."""
        wrapper = self._make_wrapper()
        wrapper.post_tool_notification("github", "PR merged")

        notif = wrapper.notification_queue.drain()[0]
        assert notif.source == NotificationSource.MCP_SERVER
        assert notif.source_name == "github"
        assert notif.message == "PR merged"

    def test_post_user_message(self):
        """post_user_message uses USER source with HIGH priority."""
        wrapper = self._make_wrapper()
        wrapper.post_user_message("Hey agent, check this")

        notif = wrapper.notification_queue.drain()[0]
        assert notif.source == NotificationSource.USER
        assert notif.source_name == "user"
        assert notif.priority == NotificationPriority.HIGH

    def test_post_user_message_custom_priority(self):
        """post_user_message priority can be overridden."""
        wrapper = self._make_wrapper()
        wrapper.post_user_message("Low urgency", priority=NotificationPriority.LOW)

        notif = wrapper.notification_queue.drain()[0]
        assert notif.priority == NotificationPriority.LOW

    # ── Budget helpers ────────────────────────────────────────────────

    def test_update_budget(self):
        """update_budget changes the context budget."""
        wrapper = self._make_wrapper()
        wrapper.update_budget(32_000)
        assert wrapper.context_budget == 32_000

    # ── Multiple posts ────────────────────────────────────────────────

    def test_multiple_posts_accumulate(self):
        """Multiple posts accumulate in the queue."""
        wrapper = self._make_wrapper()
        wrapper.post_tool_notification("a", "msg1")
        wrapper.post_tool_notification("b", "msg2")
        wrapper.post_user_message("msg3")

        assert wrapper.notification_queue.size == 3
        drained = wrapper.notification_queue.drain()
        messages = [n.message for n in drained]
        assert "msg1" in messages
        assert "msg2" in messages
        assert "msg3" in messages


# ── build_context ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestBuildContext:
    """Unit tests for HubIOWrapper.build_context()."""

    def _make_wrapper(self, **kwargs) -> HubIOWrapper:
        registry = kwargs.pop("server_registry", ServerRegistry())
        return HubIOWrapper(server_registry=registry, **kwargs)

    def test_empty_build(self):
        """Empty inputs produce empty context."""
        wrapper = self._make_wrapper()
        entries = wrapper.build_context()
        assert entries == []

    def test_system_prompt_in_foundational(self):
        """System prompt lands in Zone FOUNDATIONAL."""
        wrapper = self._make_wrapper()
        entries = wrapper.build_context(system_prompt="You are a helpful agent.")
        assert len(entries) == 1
        assert entries[0].zone == Zone.FOUNDATIONAL
        assert entries[0].source == "system_prompt"
        assert entries[0].content == "You are a helpful agent."

    def test_directives_in_foundational(self):
        """Steer directives land in Zone FOUNDATIONAL."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("be concise")
        wrapper.add_directive("use Python")
        entries = wrapper.build_context()
        directive_entries = [e for e in entries if e.source == "directive"]
        assert len(directive_entries) == 2
        assert all(e.zone == Zone.FOUNDATIONAL for e in directive_entries)
        assert all(e.importance == 1.0 for e in directive_entries)

    def test_capabilities_in_foundational(self):
        """Capabilities land in Zone FOUNDATIONAL."""
        wrapper = self._make_wrapper()
        entries = wrapper.build_context(
            capabilities=[{"name": "read_file"}, {"name": "write_file"}],
        )
        cap_entries = [e for e in entries if e.source == "capability"]
        assert len(cap_entries) == 2
        assert all(e.zone == Zone.FOUNDATIONAL for e in cap_entries)

    def test_history_in_contextual(self):
        """Turn history lands in Zone CONTEXTUAL."""
        wrapper = self._make_wrapper()
        entries = wrapper.build_context(
            turn_history=["turn1", "turn2", "turn3"],
        )
        hist_entries = [e for e in entries if e.source == "history"]
        assert len(hist_entries) == 3
        assert all(e.zone == Zone.CONTEXTUAL for e in hist_entries)

    def test_notifications_in_focal(self):
        """Notifications land in Zone FOCAL."""
        wrapper = self._make_wrapper()
        entries = wrapper.build_context(
            notifications=["build passed"],
        )
        notif_entries = [e for e in entries if e.source == "notification"]
        assert len(notif_entries) == 1
        assert notif_entries[0].zone == Zone.FOCAL

    def test_current_prompt_in_focal(self):
        """Current prompt lands in Zone FOCAL."""
        wrapper = self._make_wrapper()
        entries = wrapper.build_context(current_prompt="build auth")
        prompt_entries = [e for e in entries if e.source == "user_prompt"]
        assert len(prompt_entries) == 1
        assert prompt_entries[0].zone == Zone.FOCAL
        assert prompt_entries[0].importance == 0.9

    def test_zone_ordering(self):
        """Entries are sorted: FOUNDATIONAL → CONTEXTUAL → FOCAL."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("be brief")
        entries = wrapper.build_context(
            system_prompt="You are helpful.",
            turn_history=["old turn"],
            current_prompt="do the thing",
            notifications=["alert"],
        )
        zones = [e.zone for e in entries]
        # All FOUNDATIONAL zones come before CONTEXTUAL, before FOCAL
        assert zones == sorted(zones)

    def test_importance_ordering_within_zone(self):
        """Within same zone, entries are sorted by importance descending."""
        wrapper = self._make_wrapper()
        entries = wrapper.build_context(
            current_prompt="task",             # importance=0.9
            notifications=["alert1", "alert2"],  # importance=0.4
        )
        focal = [e for e in entries if e.zone == Zone.FOCAL]
        importances = [e.importance for e in focal]
        assert importances == sorted(importances, reverse=True)

    def test_budget_enforcement(self):
        """Entries exceeding budget are dropped."""
        # Very tight budget — only room for one small entry
        wrapper = self._make_wrapper(context_budget=10)
        entries = wrapper.build_context(
            system_prompt="short",
            turn_history=["a very long turn that uses many tokens " * 20],
            current_prompt="task",
        )
        # Should have dropped some entries
        total_tokens = sum(e.token_estimate for e in entries)
        assert total_tokens <= 10

    def test_budget_keeps_foundational_first(self):
        """Budget enforcement prioritises foundational zone entries."""
        wrapper = self._make_wrapper(context_budget=50)
        wrapper.add_directive("critical directive")
        entries = wrapper.build_context(
            system_prompt="system",
            turn_history=["x" * 200],  # 50 tokens — will bust budget
            current_prompt="task",
        )
        sources = {e.source for e in entries}
        # System prompt and directive should be included (foundational priority)
        assert "system_prompt" in sources or "directive" in sources

    def test_context_entries_property(self):
        """context_entries returns a copy of last assembled entries."""
        wrapper = self._make_wrapper()
        wrapper.build_context(system_prompt="test")
        entries = wrapper.context_entries
        assert len(entries) == 1
        assert entries[0].source == "system_prompt"
        # It's a copy
        entries.clear()
        assert len(wrapper.context_entries) == 1

    def test_total_context_tokens(self):
        """total_context_tokens sums estimates from last build."""
        wrapper = self._make_wrapper()
        wrapper.build_context(
            system_prompt="hello world",  # ~3 tokens
            current_prompt="do the thing",  # ~3 tokens
        )
        total = wrapper.total_context_tokens()
        assert total > 0

    def test_returns_context_entry_instances(self):
        """All entries are ContextEntry instances."""
        wrapper = self._make_wrapper()
        entries = wrapper.build_context(
            system_prompt="sys",
            current_prompt="go",
        )
        assert all(isinstance(e, ContextEntry) for e in entries)

    def test_turn_number_on_focal(self):
        """Focal entries get the current turn_number."""
        wrapper = self._make_wrapper()
        entries = wrapper.build_context(
            current_prompt="hello",
            turn_number=5,
        )
        assert entries[0].turn_added == 5

    def test_full_assembly(self):
        """End-to-end: all zones populated and correctly ordered."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("be helpful")
        entries = wrapper.build_context(
            system_prompt="You are an agent.",
            capabilities=[{"name": "tool_a"}],
            turn_history=["turn 1", "turn 2"],
            current_prompt="build it",
            notifications=["CI passed"],
            turn_number=3,
        )

        # Should have: system_prompt, directive, capability, 2 history, notification, prompt
        assert len(entries) == 7

        # Zone ordering preserved
        zones = [e.zone for e in entries]
        assert zones == sorted(zones)

        # Check zone membership
        by_zone = {}
        for e in entries:
            by_zone.setdefault(e.zone, []).append(e)
        assert Zone.FOUNDATIONAL in by_zone
        assert Zone.CONTEXTUAL in by_zone
        assert Zone.FOCAL in by_zone

    def test_seed_context_includes_directives(self):
        """seed_context still includes directives list."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("test directive")
        ctx = wrapper.seed_context()
        assert ctx["directives"] == ["test directive"]
