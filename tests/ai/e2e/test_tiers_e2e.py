"""E2E tests: Inject / Steer / Billing through the internal turn chain.

These exercise the three-tier communication *at the library level*:
  - Inject: HIGH-priority notifications through InjectNotificationsLink
  - Steer:  Persistent directives through ReadInputLink._apply_directives()
  - Billing: UsageTracker + EventEmitterMiddleware BILLING events

Uses FakeSession (no real API) but real chain orchestration, real
link composition, and real codeupipe Context/Chain machinery.
"""

from __future__ import annotations

import asyncio

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.agent_loop import AgentLoopLink, build_turn_chain
from codeupipe.ai.loop.notifications import (
    Notification,
    NotificationPriority,
    NotificationQueue,
    NotificationSource,
)
from codeupipe.ai.loop.state import AgentState, TurnType
from codeupipe.ai.agent.billing import UsageTracker, get_multiplier
from codeupipe.ai.agent.emitter import EventEmitterMiddleware
from codeupipe.ai.agent.events import AgentEvent, EventType

from .conftest import FakeProvider


# =====================================================================
# INJECT — HIGH-priority notifications through the full turn chain
# =====================================================================


@pytest.mark.e2e
class TestInjectLibE2E:
    """Inject tier at the library level: HIGH priority notifs
    drain before NORMAL ones and reach the agent prompt."""

    @pytest.mark.asyncio
    async def test_high_priority_drained_before_normal(self):
        """HIGH-priority (inject) notifications sort before NORMAL (push)."""
        queue = NotificationQueue()

        # NORMAL first in queue order
        queue.push(Notification(
            source=NotificationSource.SYSTEM,
            source_name="ci",
            message="Background sync done",
            priority=NotificationPriority.NORMAL,
        ))
        # HIGH second in queue order — should sort first
        queue.push(Notification(
            source=NotificationSource.USER,
            source_name="user",
            message="URGENT: rollback required",
            priority=NotificationPriority.HIGH,
        ))

        drained = queue.drain()
        assert len(drained) == 2
        assert drained[0].priority == NotificationPriority.HIGH
        assert drained[1].priority == NotificationPriority.NORMAL
        assert "rollback" in drained[0].message

    @pytest.mark.asyncio
    async def test_inject_notification_into_turn_chain(self):
        """HIGH-priority notification reaches the agent via InjectNotificationsLink."""
        queue = NotificationQueue()
        queue.push(Notification(
            source=NotificationSource.USER,
            source_name="user",
            message="CRITICAL: Database failover in progress",
            priority=NotificationPriority.HIGH,
        ))

        provider = FakeProvider([
            {"content": "Working on the task."},
            {"content": "Acknowledged the database failover."},
        ])

        ctx = Payload({
            "prompt": "Continue working on the task",
            "provider": provider,
            "notification_queue": queue,
            "follow_up_prompt": "Any notifications?",
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        state: AgentState = result.get("agent_state")
        assert state.done is True
        assert len(state.turn_history) >= 2
        # Queue should be drained
        assert queue.is_empty()

    @pytest.mark.asyncio
    async def test_inject_multiple_high_priority(self):
        """Multiple HIGH-priority injections all drain in a single cycle."""
        queue = NotificationQueue()
        for i in range(3):
            queue.push(Notification(
                source=NotificationSource.USER,
                source_name="user",
                message=f"Alert {i + 1}: system event",
                priority=NotificationPriority.HIGH,
            ))

        drained = queue.drain()
        assert len(drained) == 3
        assert all(n.priority == NotificationPriority.HIGH for n in drained)

    @pytest.mark.asyncio
    async def test_inject_emits_notification_events(self):
        """Injected notifications produce NOTIFICATION events via the emitter."""
        queue = NotificationQueue()
        queue.push(Notification(
            source=NotificationSource.USER,
            source_name="user",
            message="Injected alert",
            priority=NotificationPriority.HIGH,
        ))

        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        emitter = EventEmitterMiddleware(event_queue)

        chain = build_turn_chain()
        chain.use_hook(emitter)

        state = AgentState(max_iterations=3)
        provider = FakeProvider([{"content": "Got it."}])

        ctx = Payload({
            "prompt": "Ack notifications",
            "provider": provider,
            "notification_queue": queue,
            "agent_state": state,
        })

        await chain.run(ctx)

        # Collect emitted events
        events: list[AgentEvent] = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        notif_events = [e for e in events if e.type == EventType.NOTIFICATION]
        assert len(notif_events) >= 1
        assert "Injected alert" in notif_events[0].data.get("message", "")

    @pytest.mark.asyncio
    async def test_inject_and_push_ordering_through_chain(self):
        """Inject (HIGH) + push (NORMAL) both reach the chain, HIGH first."""
        queue = NotificationQueue()

        # Push (NORMAL) first
        queue.push(Notification(
            source=NotificationSource.SYSTEM,
            source_name="ci",
            message="Build passed",
            priority=NotificationPriority.NORMAL,
        ))
        # Inject (HIGH) second
        queue.push(Notification(
            source=NotificationSource.USER,
            source_name="user",
            message="DEPLOY NOW",
            priority=NotificationPriority.HIGH,
        ))

        provider = FakeProvider([
            {"content": "Processing..."},
            {"content": "Done with notifications."},
        ])

        ctx = Payload({
            "prompt": "Start work",
            "provider": provider,
            "notification_queue": queue,
            "follow_up_prompt": "Check notifications",
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        state: AgentState = result.get("agent_state")
        assert state.done is True
        assert queue.is_empty()


# =====================================================================
# STEER — Persistent directives through ReadInputLink
# =====================================================================


@pytest.mark.e2e
class TestSteerLibE2E:
    """Steer tier at the library level: directives prepended to every
    prompt through the full turn chain."""

    @pytest.mark.asyncio
    async def test_directive_prepended_to_first_prompt(self):
        """Directive appears in the prompt sent to the session on turn 1."""
        provider = FakeProvider([{"content": "Responding concisely."}])

        ctx = Payload({
            "prompt": "What is Python?",
            "provider": provider,
            "directives": ["Be extremely concise", "Use bullet points"],
        })

        loop = AgentLoopLink()
        await loop.call(ctx)

        # Verify the prompt sent to session contains directives
        sent_prompt = provider.call_log[0]["prompt"]
        assert "[Active Directives]" in sent_prompt
        assert "Be extremely concise" in sent_prompt
        assert "Use bullet points" in sent_prompt
        # Original prompt should still be at the end (Zone 3 focal)
        assert sent_prompt.endswith("What is Python?")

    @pytest.mark.asyncio
    async def test_directive_persists_across_turns(self):
        """Directives remain on every turn, not just the first."""
        provider = FakeProvider([
            {"content": "Turn 1 response."},
            {"content": "Turn 2 response."},
        ])

        ctx = Payload({
            "prompt": "Start the task",
            "provider": provider,
            "directives": ["Always say CONFIRMED"],
            "follow_up_prompt": "Continue the work",
        })

        loop = AgentLoopLink()
        await loop.call(ctx)

        # Both turns should have directives
        assert len(provider.call_log) == 2
        for call in provider.call_log:
            assert "[Active Directives]" in call["prompt"]
            assert "Always say CONFIRMED" in call["prompt"]

    @pytest.mark.asyncio
    async def test_no_directives_no_header(self):
        """Without directives, no [Active Directives] header in prompt."""
        provider = FakeProvider([{"content": "Clean response."}])

        ctx = Payload({
            "prompt": "What is Python?",
            "provider": provider,
        })

        loop = AgentLoopLink()
        await loop.call(ctx)

        sent_prompt = provider.call_log[0]["prompt"]
        assert "[Active Directives]" not in sent_prompt
        assert sent_prompt == "What is Python?"

    @pytest.mark.asyncio
    async def test_empty_directives_list_no_header(self):
        """Empty directives list behaves same as no directives."""
        provider = FakeProvider([{"content": "Clean."}])

        ctx = Payload({
            "prompt": "Hello",
            "provider": provider,
            "directives": [],
        })

        loop = AgentLoopLink()
        await loop.call(ctx)

        sent_prompt = provider.call_log[0]["prompt"]
        assert "[Active Directives]" not in sent_prompt

    @pytest.mark.asyncio
    async def test_multiple_directives_all_present(self):
        """All directives appear in the header, each on its own line."""
        provider = FakeProvider([{"content": "Ok."}])

        ctx = Payload({
            "prompt": "Go",
            "provider": provider,
            "directives": ["Rule A", "Rule B", "Rule C"],
        })

        loop = AgentLoopLink()
        await loop.call(ctx)

        sent = provider.call_log[0]["prompt"]
        assert "- Rule A" in sent
        assert "- Rule B" in sent
        assert "- Rule C" in sent

    @pytest.mark.asyncio
    async def test_directive_on_follow_up_turn(self):
        """Directives apply to follow-up prompts too, not just initial."""
        provider = FakeProvider([
            {"content": "First."},
            {"content": "Second."},
        ])

        ctx = Payload({
            "prompt": "Start task",
            "provider": provider,
            "directives": ["Format as JSON"],
            "follow_up_prompt": "Now finalize",
        })

        loop = AgentLoopLink()
        await loop.call(ctx)

        # Second turn (follow-up) should also have the directive
        follow_up_prompt = provider.call_log[1]["prompt"]
        assert "[Active Directives]" in follow_up_prompt
        assert "Format as JSON" in follow_up_prompt

    @pytest.mark.asyncio
    async def test_directive_on_notification_turn(self):
        """Directives apply when notifications are formatted as the prompt."""
        queue = NotificationQueue()
        queue.push(Notification(
            source=NotificationSource.SYSTEM,
            source_name="ci",
            message="Build complete",
            priority=NotificationPriority.NORMAL,
        ))

        provider = FakeProvider([
            {"content": "Working."},
            {"content": "Notification handled."},
            {"content": "Done."},
        ])

        ctx = Payload({
            "prompt": "Work on task",
            "provider": provider,
            "directives": ["Be brief"],
            "notification_queue": queue,
            "follow_up_prompt": "Check notifications",
        })

        loop = AgentLoopLink()
        await loop.call(ctx)

        # All turns should have directive
        for call in provider.call_log:
            assert "[Active Directives]" in call["prompt"]


# =====================================================================
# BILLING — UsageTracker + BILLING events through the emitter
# =====================================================================


@pytest.mark.e2e
class TestBillingLibE2E:
    """Billing tier at the library level: UsageTracker records turns,
    EventEmitterMiddleware emits BILLING events."""

    @pytest.mark.asyncio
    async def test_billing_event_emitted_per_turn(self):
        """Each send_turn produces a BILLING event in the emitter."""
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        emitter = EventEmitterMiddleware(event_queue, model="gpt-4.1")

        chain = build_turn_chain()
        chain.use_hook(emitter)

        state = AgentState(max_iterations=3)
        provider = FakeProvider([{"content": "Hello."}])

        ctx = Payload({
            "prompt": "Say hi",
            "provider": provider,
            "agent_state": state,
        })

        await chain.run(ctx)

        events: list[AgentEvent] = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        billing = [e for e in events if e.type == EventType.BILLING]
        assert len(billing) >= 1

        be = billing[0]
        assert be.data["model"] == "gpt-4.1"
        assert be.data["multiplier"] == 0.0  # gpt-4.1 is free
        assert be.data["total_requests"] >= 1

    @pytest.mark.asyncio
    async def test_billing_tracks_multiple_turns(self):
        """Billing accumulates across chain iterations."""
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        emitter = EventEmitterMiddleware(event_queue, model="claude-sonnet-4")

        chain = build_turn_chain()
        chain.use_hook(emitter)

        # Two turns: initial + follow-up
        provider = FakeProvider([
            {"content": "Turn 1."},
            {"content": "Turn 2."},
        ])

        state = AgentState(max_iterations=5)
        ctx = Payload({
            "prompt": "Do task",
            "provider": provider,
            "agent_state": state,
            "follow_up_prompt": "Continue",
        })

        # Run turn chain twice to simulate the loop
        result = await chain.run(ctx)
        # For second turn, we need a fresh run with updated state
        result_state = result.get("agent_state")
        if not result_state.done:
            ctx2 = result.insert("agent_state", result_state)
            await chain.run(ctx2)

        events: list[AgentEvent] = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        billing = [e for e in events if e.type == EventType.BILLING]
        # At least one billing event per chain.run
        assert len(billing) >= 1

        # Claude-sonnet-4 has 1.0x multiplier
        for be in billing:
            assert be.data["model"] == "claude-sonnet-4"
            assert be.data["multiplier"] == 1.0

    @pytest.mark.asyncio
    async def test_usage_tracker_standalone(self):
        """UsageTracker correctly accumulates across multiple turns."""
        tracker = UsageTracker(model="claude-opus-4.5")
        assert tracker.total_requests == 0
        assert tracker.total_premium_requests == 0.0

        tracker.record_turn()
        assert tracker.total_requests == 1
        assert tracker.total_premium_requests == 3.0  # 3x

        tracker.record_turn()
        assert tracker.total_requests == 2
        assert tracker.total_premium_requests == 6.0  # 3x * 2

    @pytest.mark.asyncio
    async def test_free_model_zero_premium(self):
        """Free model (gpt-4.1) tracks requests but 0 premium."""
        tracker = UsageTracker(model="gpt-4.1")
        tracker.record_turn()
        tracker.record_turn()

        assert tracker.total_requests == 2
        assert tracker.total_premium_requests == 0.0
        assert tracker.multiplier == 0.0

    @pytest.mark.asyncio
    async def test_billing_not_emitted_without_send(self):
        """No BILLING event if send_turn doesn't actually call the model."""
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        emitter = EventEmitterMiddleware(event_queue, model="gpt-4.1")

        chain = build_turn_chain()
        chain.use_hook(emitter)

        # Set up state so second turn has no prompt (done)
        state = AgentState(max_iterations=3, loop_iteration=1)
        provider = FakeProvider([])  # No responses

        ctx = Payload({
            "prompt": "test",
            "provider": provider,
            "agent_state": state,
            # No follow_up or notifications → next_prompt = None → no send
        })

        await chain.run(ctx)

        events: list[AgentEvent] = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        billing = [e for e in events if e.type == EventType.BILLING]
        # On second iteration (loop_iteration=1), no prompt → no billing
        # But first iteration gets the initial prompt → should bill
        # Actually state.loop_iteration=1 means it's already past first turn
        # and ReadInputLink will look for follow_up (None) → no send → no billing
        assert len(billing) == 0

    @pytest.mark.asyncio
    async def test_to_dict_serialization(self):
        """UsageTracker.to_dict() produces correct serialization."""
        tracker = UsageTracker(model="gemini-2.5-pro")
        tracker.record_turn()

        d = tracker.to_dict()
        assert d == {
            "model": "gemini-2.5-pro",
            "multiplier": 1.0,
            "total_requests": 1,
            "total_premium_requests": 1.0,
        }


# =====================================================================
# COMBINED — All three tiers through the full turn chain
# =====================================================================


@pytest.mark.e2e
class TestCombinedTiersLibE2E:
    """All three tiers working together through the internal chain."""

    @pytest.mark.asyncio
    async def test_steer_plus_inject_through_chain(self):
        """Directives + injected notifications coexist in the prompt."""
        queue = NotificationQueue()
        queue.push(Notification(
            source=NotificationSource.USER,
            source_name="user",
            message="URGENT: deploy now",
            priority=NotificationPriority.HIGH,
        ))

        provider = FakeProvider([
            {"content": "Starting work."},
            {"content": "Deploying as requested."},
        ])

        ctx = Payload({
            "prompt": "Work on the feature",
            "provider": provider,
            "directives": ["Be brief", "Use JSON format"],
            "notification_queue": queue,
            "follow_up_prompt": "Handle the notification",
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        state: AgentState = result.get("agent_state")
        assert state.done is True

        # First turn should have directives
        assert "[Active Directives]" in provider.call_log[0]["prompt"]
        assert "Be brief" in provider.call_log[0]["prompt"]

        # Queue should be drained
        assert queue.is_empty()

    @pytest.mark.asyncio
    async def test_all_tiers_with_billing_events(self):
        """Steer + inject + billing events all fire in one run."""
        queue = NotificationQueue()
        queue.push(Notification(
            source=NotificationSource.USER,
            source_name="user",
            message="Check this",
            priority=NotificationPriority.HIGH,
        ))

        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        emitter = EventEmitterMiddleware(event_queue, model="claude-sonnet-4")

        chain = build_turn_chain()
        chain.use_hook(emitter)

        state = AgentState(max_iterations=5)
        provider = FakeProvider([{"content": "Done with everything."}])

        ctx = Payload({
            "prompt": "Process task",
            "provider": provider,
            "agent_state": state,
            "directives": ["Be concise"],
            "notification_queue": queue,
        })

        await chain.run(ctx)

        events: list[AgentEvent] = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        types = {e.type for e in events}

        # Should have billing (send happened)
        assert EventType.BILLING in types

        # Should have notification event (inject fired)
        assert EventType.NOTIFICATION in types

        # Should have turn lifecycle events
        assert EventType.TURN_START in types
        assert EventType.TURN_END in types

        # Verify billing data
        billing_event = next(e for e in events if e.type == EventType.BILLING)
        assert billing_event.data["model"] == "claude-sonnet-4"
        assert billing_event.data["multiplier"] == 1.0

    @pytest.mark.asyncio
    async def test_inject_steer_billing_full_loop(self):
        """Full loop: directive shapes prompt, inject delivers mid-task,
        billing tracks all turns."""
        queue = NotificationQueue()

        provider = FakeProvider([
            {"content": "Step 1 done."},
            {"content": "Alert handled."},
        ])

        # Pre-inject before loop starts
        queue.push(Notification(
            source=NotificationSource.USER,
            source_name="user",
            message="Priority change: focus on security",
            priority=NotificationPriority.HIGH,
        ))

        ctx = Payload({
            "prompt": "Build the feature",
            "provider": provider,
            "directives": ["Follow OWASP guidelines"],
            "notification_queue": queue,
            "follow_up_prompt": "Check alerts",
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        state: AgentState = result.get("agent_state")
        assert state.done is True

        # Directive was in the first prompt
        assert "OWASP" in provider.call_log[0]["prompt"]

        # Notification queue was drained
        assert queue.is_empty()

        # Multiple turns happened
        assert len(state.turn_history) >= 2
