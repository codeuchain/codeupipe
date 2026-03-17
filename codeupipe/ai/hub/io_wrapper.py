"""HubIOWrapper — Coordinator for hub-level I/O around the agent loop.

The lifecycle doc says: "The hub is not inside the loop — it wraps
the loop. Every piece of information that enters or exits the agent
passes through it."

This class owns:
  - ServerRegistry     — tool routing to MCP servers
  - NotificationQueue  — async backchannel from servers/users/timers
  - context_budget     — token budget for context pruning decisions
  - directives         — persistent context directives (steer)

Links inside the turn chain read from the wrapper's queue and
use the wrapper's context_budget for pruning.  The wrapper itself
is placed on context so any link can interact with it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from codeupipe.ai.hub.registry import ServerRegistry
from codeupipe.ai.loop.context_schema import (
    ContextEntry,
    Zone,
    get_importance,
)
from codeupipe.ai.loop.notifications import (
    Notification,
    NotificationPriority,
    NotificationQueue,
    NotificationSource,
)

logger = logging.getLogger("codeupipe.ai.hub")


@dataclass
class HubIOWrapper:
    """Coordinates hub I/O around the agent loop.

    Attributes:
        server_registry: Routes tool calls to owning MCP servers.
        notification_queue: Thread-safe queue for backchannel delivery.
        context_budget: Max tokens the agent's context should consume.
    """

    server_registry: ServerRegistry
    notification_queue: NotificationQueue = field(
        default_factory=NotificationQueue,
    )
    context_budget: int = 128_000
    directives: list[str] = field(default_factory=list)
    _context_entries: list[ContextEntry] = field(
        default_factory=list, repr=False,
    )

    # ── Context assembly ──────────────────────────────────────────────

    def build_context(
        self,
        *,
        system_prompt: str = "",
        turn_history: list | None = None,
        capabilities: list | None = None,
        current_prompt: str = "",
        notifications: list | None = None,
        turn_number: int = 0,
    ) -> list[ContextEntry]:
        """Assemble a zone-ordered list of ContextEntries.

        Collects all pending context (directives, history, notifications,
        current prompt) into typed ContextEntry objects, classifies each
        into Zone 1/2/3, and returns them sorted for positional ordering:
        FOUNDATIONAL first → CONTEXTUAL middle → FOCAL last.

        The returned list respects the context_budget — entries are
        included in priority order (zone, then importance) until the
        budget is exhausted.

        This centralises context construction that was previously
        spread across multiple links (Route 4).
        """
        entries: list[ContextEntry] = []

        # Zone 1 — FOUNDATIONAL: system prompt
        if system_prompt:
            entries.append(ContextEntry(
                zone=Zone.FOUNDATIONAL,
                source="system_prompt",
                content=system_prompt,
                importance=get_importance("system_prompt"),
                turn_added=0,
            ))

        # Zone 1 — FOUNDATIONAL: directives (steer)
        for directive in self.directives:
            entries.append(ContextEntry(
                zone=Zone.FOUNDATIONAL,
                source="directive",
                content=directive,
                importance=get_importance("directive"),
                turn_added=0,
            ))

        # Zone 1 — FOUNDATIONAL: capabilities
        for cap in (capabilities or []):
            cap_text = str(cap)
            entries.append(ContextEntry(
                zone=Zone.FOUNDATIONAL,
                source="capability",
                content=cap_text,
                importance=get_importance("capability"),
                turn_added=0,
            ))

        # Zone 2 — CONTEXTUAL: conversation history
        for i, turn in enumerate(turn_history or []):
            turn_text = str(turn)
            entries.append(ContextEntry(
                zone=Zone.CONTEXTUAL,
                source="history",
                content=turn_text,
                importance=get_importance("history"),
                turn_added=i,
            ))

        # Zone 3 — FOCAL: notifications
        for notif in (notifications or []):
            notif_text = str(notif)
            entries.append(ContextEntry(
                zone=Zone.FOCAL,
                source="notification",
                content=notif_text,
                importance=get_importance("notification"),
                turn_added=turn_number,
            ))

        # Zone 3 — FOCAL: current prompt
        if current_prompt:
            entries.append(ContextEntry(
                zone=Zone.FOCAL,
                source="user_prompt",
                content=current_prompt,
                importance=get_importance("user_prompt"),
                turn_added=turn_number,
            ))

        # Sort: zone ascending (foundational first), importance descending
        entries.sort(key=lambda e: (e.zone, -e.importance))

        # Enforce budget — include entries until budget is exhausted
        budgeted: list[ContextEntry] = []
        total_tokens = 0
        for entry in entries:
            if total_tokens + entry.token_estimate > self.context_budget:
                logger.debug(
                    "Budget exceeded at %d tokens — dropping %s (%s)",
                    total_tokens,
                    entry.source,
                    entry.zone.name,
                )
                continue
            budgeted.append(entry)
            total_tokens += entry.token_estimate

        self._context_entries = budgeted
        logger.debug(
            "Built context: %d entries, %d tokens (budget: %d)",
            len(budgeted),
            total_tokens,
            self.context_budget,
        )
        return budgeted

    @property
    def context_entries(self) -> list[ContextEntry]:
        """Last assembled context entries (read-only snapshot)."""
        return list(self._context_entries)

    def total_context_tokens(self) -> int:
        """Sum of token estimates in the last assembled context."""
        return sum(e.token_estimate for e in self._context_entries)

    # ── Context seeding ───────────────────────────────────────────────

    def seed_context(self) -> dict:
        """Produce context keys for injection at loop start.

        Returns a dict that should be merged into the Chain context
        before the first loop iteration so inner links can find the
        notification_queue and context_budget without coupling to this
        class directly.
        """
        return {
            "notification_queue": self.notification_queue,
            "context_budget": self.context_budget,
            "hub_io": self,
            "directives": list(self.directives),
        }

    # ── Backchannel helpers ───────────────────────────────────────────

    def post_notification(
        self,
        source: NotificationSource,
        source_name: str,
        message: str,
        *,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        metadata: dict | None = None,
    ) -> None:
        """Convenience method for external sources to post to the queue.

        Thread-safe — can be called from MCP server threads, timers,
        or the user backchannel.
        """
        notification = Notification(
            source=source,
            source_name=source_name,
            message=message,
            priority=priority,
            metadata=metadata,
        )
        self.notification_queue.push(notification)
        logger.debug(
            "Hub received notification from %s/%s: %s",
            source,
            source_name,
            message[:80],
        )

    def post_tool_notification(
        self,
        server_name: str,
        message: str,
        *,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        metadata: dict | None = None,
    ) -> None:
        """Shorthand for MCP-server backchannel posts."""
        self.post_notification(
            source=NotificationSource.MCP_SERVER,
            source_name=server_name,
            message=message,
            priority=priority,
            metadata=metadata,
        )

    def post_user_message(
        self,
        message: str,
        *,
        priority: NotificationPriority = NotificationPriority.HIGH,
    ) -> None:
        """Post a user backchannel message (mid-task injection)."""
        self.post_notification(
            source=NotificationSource.USER,
            source_name="user",
            message=message,
            priority=priority,
        )

    # ── Budget helpers ────────────────────────────────────────────────

    def update_budget(self, new_budget: int) -> None:
        """Adjust the context budget (e.g. after model reconfig)."""
        self.context_budget = new_budget

    # ── Directive helpers ─────────────────────────────────────────────

    def add_directive(self, directive: str) -> None:
        """Add a persistent context directive (steer).

        Directives are prepended to every prompt the agent builds,
        shaping its behavior without consuming an API request.
        """
        self.directives.append(directive)
        logger.debug("Hub directive added: %s", directive[:80])

    def remove_directive(self, directive: str) -> None:
        """Remove a specific directive (no-op if not found)."""
        try:
            self.directives.remove(directive)
            logger.debug("Hub directive removed: %s", directive[:80])
        except ValueError:
            pass  # Not found — safe no-op

    def clear_directives(self) -> None:
        """Remove all persistent directives."""
        self.directives.clear()
        logger.debug("Hub directives cleared")
