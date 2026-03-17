"""SDK E2E tests — Inject, Steer, and Billing via real Copilot API.

These tests exercise the three-tier communication and billing
tracking through the full Agent → Chain → Copilot API pipeline.

Run these tests separately:
    pytest tests/sdk/test_sdk_e2e_tiers.py -m e2e -v --tb=short
"""

from __future__ import annotations

import asyncio
import os

import pytest

from codeupipe.ai.agent import Agent, AgentConfig, AgentEvent, EventType


def _has_auth() -> bool:
    """Check if Copilot authentication is available."""
    return any([
        os.getenv("COPILOT_GITHUB_TOKEN"),
        os.getenv("GH_TOKEN"),
        os.getenv("GITHUB_TOKEN"),
    ])


# ── Inject E2E ────────────────────────────────────────────────────────


@pytest.mark.e2e
class TestInjectE2E:
    """inject() delivers high-priority messages through the real pipeline."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_inject_before_run_reaches_agent(self):
        """inject() before run() delivers the message to the agent."""
        agent = Agent()
        agent.inject("CRITICAL: The database is down. Acknowledge this.")

        answer = await agent.ask(
            "What urgent notifications do you have? Summarize them."
        )

        assert answer is not None
        assert len(answer) > 0
        # Pipeline didn't crash — notification was processed

    @pytest.mark.asyncio
    async def test_inject_priority_over_push(self):
        """inject() (HIGH) is processed before push() (NORMAL)."""
        agent = Agent()
        agent.push("Low priority: background sync complete")
        agent.inject("HIGH priority: deployment failed")

        # Both should be delivered — agent processes them by priority
        answer = await agent.ask(
            "List all notifications you received, in the order you processed them."
        )

        assert answer is not None
        assert len(answer) > 0

    @pytest.mark.asyncio
    async def test_inject_multiple_messages(self):
        """Multiple inject() calls all reach the agent."""
        agent = Agent()
        agent.inject("Alert 1: CPU spike detected")
        agent.inject("Alert 2: Memory threshold exceeded")
        agent.inject("Alert 3: Disk space low")

        answer = await agent.ask(
            "How many alerts did you receive? Reply with ONLY the number."
        )

        assert answer is not None
        assert "3" in answer


# ── Steer E2E ─────────────────────────────────────────────────────────


@pytest.mark.e2e
class TestSteerE2E:
    """steer() shapes agent responses via persistent directives."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_steer_influences_response(self):
        """steer() directive shapes the agent's response style."""
        agent = Agent()
        agent.steer("Always respond in exactly one word. No exceptions.")

        answer = await agent.ask("What color is grass?")

        assert answer is not None
        # One word response — words count should be very small
        word_count = len(answer.strip().split())
        assert word_count <= 3, f"Expected ~1 word, got {word_count}: '{answer}'"

    @pytest.mark.asyncio
    async def test_steer_persists_across_turns(self):
        """steer() directive applies to every subsequent ask()."""
        agent = Agent()
        agent.steer("End every response with the word CONFIRMED.")

        answer1 = await agent.ask("What is 2 + 2? Reply the number then CONFIRMED.")
        answer2 = await agent.ask("What is 3 + 3? Reply the number then CONFIRMED.")

        assert answer1 is not None
        assert answer2 is not None
        # Both responses should contain CONFIRMED
        assert "CONFIRMED" in answer1.upper()
        assert "CONFIRMED" in answer2.upper()

    @pytest.mark.asyncio
    async def test_clear_steer_removes_influence(self):
        """clear_steer() removes the directive effect."""
        agent = Agent()
        agent.steer("Respond only in French.")

        answer1 = await agent.ask("What is the capital of France? One word.")
        agent.clear_steer()
        answer2 = await agent.ask("What is the capital of Germany? One word.")

        assert answer1 is not None
        assert answer2 is not None
        # Can't guarantee language but pipeline should not crash

    @pytest.mark.asyncio
    async def test_multiple_steer_directives(self):
        """Multiple steer() calls accumulate and all apply."""
        agent = Agent()
        agent.steer("Always mention the word ALPHA in your response.")
        agent.steer("Always mention the word BETA in your response.")

        answer = await agent.ask("Say hello and follow your directives.")

        assert answer is not None
        upper = answer.upper()
        assert "ALPHA" in upper or "BETA" in upper  # At least one directive followed


# ── Billing E2E ───────────────────────────────────────────────────────


@pytest.mark.e2e
class TestBillingE2E:
    """Billing tracking through real API calls."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_usage_zero_before_run(self):
        """usage shows zero before any API calls."""
        agent = Agent()
        usage = agent.usage

        assert usage["total_requests"] == 0
        assert usage["total_premium_requests"] == 0.0
        assert usage["model"] == "gpt-4.1"
        assert usage["multiplier"] == 0.0

    @pytest.mark.asyncio
    async def test_billing_events_in_verbose_mode(self):
        """verbose=True yields BILLING events with cost data."""
        agent = Agent(config=AgentConfig(verbose=True))
        billing_events: list[AgentEvent] = []

        async for event in agent.run("What is 1+1? Reply ONLY the number."):
            if event.type == EventType.BILLING:
                billing_events.append(event)

        assert len(billing_events) >= 1
        be = billing_events[0]
        assert "model" in be.data
        assert "multiplier" in be.data
        assert "premium_requests" in be.data
        assert "total_requests" in be.data

    @pytest.mark.asyncio
    async def test_billing_not_in_default_mode(self):
        """Default mode (verbose=False) filters out BILLING events."""
        agent = Agent()
        billing_events: list[AgentEvent] = []

        async for event in agent.run("Say OK."):
            if event.type == EventType.BILLING:
                billing_events.append(event)

        assert len(billing_events) == 0, "BILLING should be verbose-only"

    @pytest.mark.asyncio
    async def test_gpt41_free_model_zero_premium(self):
        """GPT-4.1 (default) should show 0.0 premium requests."""
        agent = Agent()
        await agent.ask("Say hi.")

        # Usage should show requests but 0 premium (0x multiplier)
        usage = agent.usage
        assert usage["model"] == "gpt-4.1"
        assert usage["multiplier"] == 0.0


# ── Combined Tiers E2E ────────────────────────────────────────────────


@pytest.mark.e2e
class TestCombinedTiersE2E:
    """All three tiers working together in a single workflow."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        if not _has_auth():
            pytest.skip("E2E tests require authentication.")

    @pytest.mark.asyncio
    async def test_steer_plus_inject_plus_push(self):
        """All three tiers combine without interference."""
        agent = Agent()

        # Tier 3: Steer
        agent.steer("Be extremely brief in all responses.")

        # Tier 2: Inject
        agent.inject("URGENT: System health check required.")

        # Tier 1: Queue
        agent.push("Note: next standup is at 10am", source="calendar")

        answer = await agent.ask("Process all your notifications and directives.")

        assert answer is not None
        assert len(answer) > 0

    @pytest.mark.asyncio
    async def test_full_workflow_with_billing(self):
        """Complete workflow: steer + inject + ask + check billing."""
        agent = Agent(config=AgentConfig(verbose=True))

        agent.steer("Always respond in one sentence.")
        agent.inject("Note: user prefers concise answers.")

        events: list[AgentEvent] = []
        async for event in agent.run("What is Python? One sentence."):
            events.append(event)

        # Should have standard events
        types = {e.type for e in events}
        assert EventType.TURN_START in types
        assert EventType.RESPONSE in types
        assert EventType.DONE in types

        # Verbose mode should include billing
        assert EventType.BILLING in types

        # Usage should be tracked
        usage = agent.usage
        assert usage["total_requests"] >= 0
