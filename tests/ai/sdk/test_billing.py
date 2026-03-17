"""RED PHASE — Tests for billing tracking.

Billing tracks premium request consumption based on model multipliers.
Each send_and_wait call = 1 premium request × model multiplier.

The emitter hooks into send_turn (after) to emit a BILLING event.
Agent.usage provides cumulative stats.

MODEL_MULTIPLIERS maps model names to their Copilot billing multiplier.
"""

import pytest


class TestModelMultipliers:
    """MODEL_MULTIPLIERS maps model names to billing multipliers."""

    def test_gpt_41_is_free(self):
        """GPT-4.1 has 0x multiplier (free on paid plans)."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["gpt-4.1"] == 0.0

    def test_gpt_4o_is_free(self):
        """GPT-4o has 0x multiplier."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["gpt-4o"] == 0.0

    def test_gpt_5_mini_is_free(self):
        """GPT-5 mini has 0x multiplier."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["gpt-5-mini"] == 0.0

    def test_claude_haiku_45(self):
        """Claude Haiku 4.5 has 0.33x multiplier."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["claude-haiku-4.5"] == 0.33

    def test_claude_sonnet_4(self):
        """Claude Sonnet 4 has 1x multiplier."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["claude-sonnet-4"] == 1.0

    def test_claude_opus_45(self):
        """Claude Opus 4.5 has 3x multiplier."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["claude-opus-4.5"] == 3.0

    def test_claude_opus_46(self):
        """Claude Opus 4.6 has 3x multiplier."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["claude-opus-4.6"] == 3.0

    def test_claude_opus_4(self):
        """Claude Opus 4 has 10x multiplier."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["claude-opus-4"] == 10.0

    def test_gemini_flash(self):
        """Gemini 3 Flash has 0.33x multiplier."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["gemini-3-flash"] == 0.33

    def test_gemini_pro(self):
        """Gemini 2.5 Pro has 1x multiplier."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["gemini-2.5-pro"] == 1.0

    def test_gpt_5(self):
        """GPT-5 has 1x multiplier."""
        from codeupipe.ai.agent.billing import MODEL_MULTIPLIERS

        assert MODEL_MULTIPLIERS["gpt-5"] == 1.0


class TestGetMultiplier:
    """get_multiplier() resolves a model name to its billing multiplier."""

    def test_known_model(self):
        """Known model returns its multiplier."""
        from codeupipe.ai.agent.billing import get_multiplier

        assert get_multiplier("gpt-4.1") == 0.0
        assert get_multiplier("claude-sonnet-4") == 1.0

    def test_unknown_model_defaults_to_one(self):
        """Unknown model defaults to 1.0x (safe billing assumption)."""
        from codeupipe.ai.agent.billing import get_multiplier

        assert get_multiplier("some-future-model") == 1.0


class TestUsageTracker:
    """UsageTracker accumulates billing data across turns."""

    def test_initial_state(self):
        """Fresh tracker has zero usage."""
        from codeupipe.ai.agent.billing import UsageTracker

        tracker = UsageTracker(model="gpt-4.1")
        assert tracker.total_requests == 0
        assert tracker.total_premium_requests == 0.0
        assert tracker.model == "gpt-4.1"

    def test_record_turn_increments(self):
        """record_turn() increments request count and premium total."""
        from codeupipe.ai.agent.billing import UsageTracker

        tracker = UsageTracker(model="claude-sonnet-4")
        tracker.record_turn()
        assert tracker.total_requests == 1
        assert tracker.total_premium_requests == 1.0

    def test_record_turn_free_model(self):
        """Free model (0x) increments requests but not premium."""
        from codeupipe.ai.agent.billing import UsageTracker

        tracker = UsageTracker(model="gpt-4.1")
        tracker.record_turn()
        tracker.record_turn()
        assert tracker.total_requests == 2
        assert tracker.total_premium_requests == 0.0

    def test_record_turn_fractional_model(self):
        """0.33x model accumulates fractional premium requests."""
        from codeupipe.ai.agent.billing import UsageTracker

        tracker = UsageTracker(model="claude-haiku-4.5")
        tracker.record_turn()
        tracker.record_turn()
        tracker.record_turn()
        assert tracker.total_requests == 3
        assert tracker.total_premium_requests == pytest.approx(0.99)

    def test_record_turn_expensive_model(self):
        """10x model accumulates 10 premium requests per turn."""
        from codeupipe.ai.agent.billing import UsageTracker

        tracker = UsageTracker(model="claude-opus-4")
        tracker.record_turn()
        assert tracker.total_premium_requests == 10.0

    def test_to_dict(self):
        """to_dict() returns serializable summary."""
        from codeupipe.ai.agent.billing import UsageTracker

        tracker = UsageTracker(model="claude-sonnet-4")
        tracker.record_turn()
        tracker.record_turn()

        d = tracker.to_dict()
        assert d["model"] == "claude-sonnet-4"
        assert d["multiplier"] == 1.0
        assert d["total_requests"] == 2
        assert d["total_premium_requests"] == 2.0

    def test_multiplier_property(self):
        """multiplier property returns the model's billing rate."""
        from codeupipe.ai.agent.billing import UsageTracker

        tracker = UsageTracker(model="claude-opus-4.5")
        assert tracker.multiplier == 3.0


class TestBillingEventType:
    """BILLING event type exists and is verbose."""

    def test_billing_event_type_exists(self):
        """EventType has a BILLING member."""
        from codeupipe.ai.agent.events import EventType

        assert hasattr(EventType, "BILLING")
        assert EventType.BILLING == "billing"

    def test_billing_is_verbose(self):
        """BILLING events are verbose (not emitted by default)."""
        from codeupipe.ai.agent.events import AgentEvent, EventType, _VERBOSE_TYPES

        assert EventType.BILLING in _VERBOSE_TYPES


class TestEmitterBillingEvent:
    """EventEmitterMiddleware emits BILLING event after language_model."""

    @pytest.mark.asyncio
    async def test_billing_event_emitted_after_language_model(self):
        """Emitter fires BILLING after language_model completes."""
        import asyncio

        from codeupipe.ai.agent.emitter import EventEmitterMiddleware
        from codeupipe.ai.agent.events import AgentEvent, EventType

        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        emitter = EventEmitterMiddleware(queue, model="claude-sonnet-4")

        # Simulate a language_model link
        link = _make_link("LanguageModelLink")
        ctx = _make_ctx(next_prompt="hello", response="answer")

        await emitter.after(link, ctx)

        events = _drain_queue(queue)
        billing_events = [e for e in events if e.type == EventType.BILLING]
        assert len(billing_events) == 1
        assert billing_events[0].data["model"] == "claude-sonnet-4"
        assert billing_events[0].data["multiplier"] == 1.0
        assert billing_events[0].data["premium_requests"] == 1.0

    @pytest.mark.asyncio
    async def test_no_billing_when_no_prompt_sent(self):
        """No BILLING event when language_model skipped (next_prompt was None)."""
        import asyncio

        from codeupipe.ai.agent.emitter import EventEmitterMiddleware
        from codeupipe.ai.agent.events import AgentEvent, EventType

        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        emitter = EventEmitterMiddleware(queue, model="gpt-4.1")

        link = _make_link("LanguageModelLink")
        ctx = _make_ctx(next_prompt=None, response=None)

        await emitter.after(link, ctx)

        events = _drain_queue(queue)
        billing_events = [e for e in events if e.type == EventType.BILLING]
        assert len(billing_events) == 0

    @pytest.mark.asyncio
    async def test_billing_free_model_still_emits(self):
        """Free model still emits BILLING event with 0.0 premium."""
        import asyncio

        from codeupipe.ai.agent.emitter import EventEmitterMiddleware
        from codeupipe.ai.agent.events import AgentEvent, EventType

        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        emitter = EventEmitterMiddleware(queue, model="gpt-4.1")

        link = _make_link("LanguageModelLink")
        ctx = _make_ctx(next_prompt="hello", response="answer")

        await emitter.after(link, ctx)

        events = _drain_queue(queue)
        billing_events = [e for e in events if e.type == EventType.BILLING]
        assert len(billing_events) == 1
        assert billing_events[0].data["premium_requests"] == 0.0


class TestAgentUsage:
    """Agent.usage returns cumulative billing info."""

    def test_usage_before_run(self):
        """usage returns zero before any runs."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        usage = agent.usage
        assert usage["total_requests"] == 0
        assert usage["total_premium_requests"] == 0.0
        assert usage["model"] == "gpt-4.1"


# ── Test helpers ──────────────────────────────────────────────────────


def _make_link(class_name: str):
    """Create a mock link object with the given class name."""
    cls = type(class_name, (), {})
    return cls()


def _make_ctx(**kwargs):
    """Create a mock context that supports .get()."""
    class MockCtx:
        def __init__(self, data):
            self._data = data
        def get(self, key, default=None):
            return self._data.get(key, default)
    return MockCtx(kwargs)


def _drain_queue(queue):
    """Drain all events from an asyncio.Queue."""
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events
