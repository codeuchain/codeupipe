"""Agent — the primary SDK entry point.

This is the ONE thing consumers import. Everything else is below
the waterline.

Usage:
    from codeupipe.ai.agent import Agent

    agent = Agent()
    async for event in agent.run("What tools do you have?"):
        print(event)

    # Or the simple way:
    answer = await agent.ask("Summarize this file")
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from codeupipe.ai.loop.notifications import (
    Notification,
    NotificationPriority,
    NotificationQueue,
    NotificationSource,
)

from codeupipe.ai.agent.billing import UsageTracker
from codeupipe.ai.agent.config import AgentConfig
from codeupipe.ai.agent.emitter import EventEmitterMiddleware
from codeupipe.ai.agent.events import AgentEvent, EventType

logger = logging.getLogger("codeupipe.ai.agent")


class Agent:
    """High-level agent interface.

    Create an Agent, call run() for streaming events or ask() for
    a simple string response. Each run() call creates a fresh session
    but can resume conversation context via session_id.

    Args:
        config: Optional AgentConfig for customization.
    """

    def __init__(self, config: AgentConfig | None = None) -> None:
        self._config = config or AgentConfig()
        self._notification_queue = NotificationQueue()
        self._directives: list[str] = []
        self._usage_tracker = UsageTracker(model=self._config.model)
        self._cancelled = False

    @property
    def config(self) -> AgentConfig:
        """The agent's configuration."""
        return self._config

    async def run(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Run the agent and yield events as they occur.

        This is the primary interface. Each call creates a fresh session.
        Events are filtered based on config (verbose, event_types).

        Args:
            prompt: The user's input prompt.

        Yields:
            AgentEvent objects as the agent processes.
        """
        self._cancelled = False
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()

        # Run the chain in a background task, emitting events to queue
        task = asyncio.create_task(self._execute(prompt, queue))

        try:
            while True:
                # Wait for next event or task completion
                if task.done():
                    # Drain remaining events
                    while not queue.empty():
                        event = queue.get_nowait()
                        if self._should_yield(event):
                            yield event
                    # Propagate any exception from the task
                    task.result()
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.1)
                    if self._should_yield(event):
                        yield event
                    if event.type == EventType.DONE:
                        break
                except asyncio.TimeoutError:
                    continue
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def ask(self, prompt: str) -> str | None:
        """Send a prompt and return just the final response string.

        Convenience method that consumes the full event stream and
        returns only the final text response.

        Args:
            prompt: The user's input prompt.

        Returns:
            The agent's response text, or None if no response.
        """
        last_response: str | None = None
        async for event in self.run(prompt):
            if event.type == EventType.RESPONSE:
                last_response = event.data.get("content")
            elif event.type == EventType.DONE:
                if last_response is None:
                    last_response = event.data.get("final_response")
        return last_response

    def push(self, message: str, source: str = "user") -> None:
        """Inject a notification into the agent's queue.

        The notification will be picked up by InjectNotificationsLink
        on the next loop iteration.

        Args:
            message: The notification message.
            source: Source identifier (default: "user").
        """
        notification = Notification(
            source=NotificationSource.USER,
            source_name=source,
            message=message,
            priority=NotificationPriority.NORMAL,
        )
        self._notification_queue.push(notification)

    def cancel(self) -> None:
        """Signal the agent to stop after the current turn."""
        self._cancelled = True

    # ── Inject (high-priority notification) ──────────────────────────

    def inject(
        self,
        message: str,
        source: str = "user",
        priority: NotificationPriority = NotificationPriority.HIGH,
    ) -> None:
        """Inject a high-priority notification into the agent's queue.

        Unlike push() (NORMAL priority), inject() uses HIGH priority
        so it sorts ahead of queued notifications. The agent reads it
        on its next drain cycle without ending the current turn.

        This is the SDK-level convenience for the inject tier.
        The hub MCP server can also call HubIOWrapper.post_user_message()
        directly for the same effect.

        Args:
            message: The notification message.
            source: Source identifier (default: "user").
            priority: Priority level (default: HIGH).
        """
        notification = Notification(
            source=NotificationSource.USER,
            source_name=source,
            message=message,
            priority=priority,
        )
        self._notification_queue.push(notification)

    # ── Steer (persistent context directives) ────────────────────────

    def steer(self, directive: str) -> None:
        """Add a persistent context directive.

        Directives are prepended to every prompt the agent builds
        (Zone 1 — foundational positioning). This shapes the agent's
        behavior without consuming an API request.

        Args:
            directive: The directive text.
        """
        self._directives.append(directive)

    def unsteer(self, directive: str) -> None:
        """Remove a specific directive (no-op if not found)."""
        try:
            self._directives.remove(directive)
        except ValueError:
            pass

    def clear_steer(self) -> None:
        """Remove all persistent directives."""
        self._directives.clear()

    @property
    def directives(self) -> list[str]:
        """Current persistent context directives."""
        return list(self._directives)

    # ── Usage / Billing ──────────────────────────────────────────────

    @property
    def usage(self) -> dict:
        """Cumulative billing usage summary."""
        return self._usage_tracker.to_dict()

    # ── Internal ─────────────────────────────────────────────────────

    async def _execute(self, prompt: str, queue: asyncio.Queue[AgentEvent]) -> None:
        """Run the full agent session chain with event emission.

        This is the internal method that wires up the chain, attaches
        the EventEmitterMiddleware, builds context, and runs.

        The middleware is attached to the *inner* turn chain (not the
        outer session chain) so it observes per-link events like
        read_input, process_response, and check_done.
        """
        from codeupipe import Payload

        from codeupipe.ai.pipelines.agent_session import build_agent_session_chain
        from codeupipe.ai.hub.server import create_default_hub
        from codeupipe.ai.filters.loop.agent_loop import build_turn_chain

        # Build the turn chain and attach the event emitter middleware
        turn_chain = build_turn_chain()
        emitter = EventEmitterMiddleware(queue, model=self._config.model)
        turn_chain.use_hook(emitter)

        # Build session chain, passing the instrumented turn chain
        chain = build_agent_session_chain(turn_chain=turn_chain)

        # Build hub (default or custom servers)
        registry = self._build_hub()

        # Build context
        ctx_data: dict[str, Any] = {
            "registry": registry,
            "model": self._config.model,
            "prompt": prompt,
            "max_iterations": self._config.max_iterations,
            "notification_queue": self._notification_queue,
            "directives": list(self._directives),
        }

        # Attach capability registry if discovery is enabled
        if self._config.auto_discover:
            try:
                from codeupipe.ai.config import get_settings
                from codeupipe.ai.discovery.registry import CapabilityRegistry

                settings = get_settings()
                registry_path = self._config.registry_path or settings.registry_path
                cap_registry = CapabilityRegistry(registry_path)
                ctx_data["capability_registry"] = cap_registry
            except ImportError:
                pass  # Discovery extras not installed

        ctx = Payload(ctx_data)
        await chain.run(ctx)

    def _build_hub(self):
        """Build the server hub from config or defaults."""
        from codeupipe.ai.hub.server import create_default_hub

        if self._config.servers:
            from codeupipe.ai.hub.config import HubConfig, ServerConfig
            from codeupipe.ai.hub.registry import ServerRegistry

            server_configs = {}
            for name, sdef in self._config.servers.items():
                sc_kwargs: dict[str, Any] = {"name": name, "tools": ["*"]}
                if sdef.url:
                    sc_kwargs["url"] = sdef.url
                elif sdef.command:
                    sc_kwargs["command"] = sdef.command
                    sc_kwargs["args"] = sdef.args or []
                server_configs[name] = ServerConfig(**sc_kwargs)

            config = HubConfig(servers=server_configs)
            registry = ServerRegistry()
            for sc in config.servers.values():
                registry.register(sc)
            return registry

        return create_default_hub()

    def _should_yield(self, event: AgentEvent) -> bool:
        """Determine if an event should be yielded based on config filters."""
        # Event type filter (most specific)
        if self._config.event_types is not None:
            return event.type in self._config.event_types

        # Verbose filter
        if event.is_verbose and not self._config.verbose:
            return False

        return True
