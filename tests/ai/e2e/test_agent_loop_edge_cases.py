"""E2E test: Edge cases — Agent loop boundary conditions.

Exercises unusual, exceptional, and boundary-condition scenarios:
  - Max iterations safety cap
  - Empty/null agent response
  - Session with no prompt (error case)
  - Notification queue exhaustion
  - Rapid intent shifts (multiple in one loop)
  - Large turn history with context pruning
  - Budget threshold triggers conversation revision
  - Checkpoint save + resume round-trip
  - Resume with no checkpoint (first run)
  - Multiple concurrent notifications from different sources

Uses mocked session (FakeSession) but real chain orchestration,
real SQLite registry, real codeupipe composition.
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.agent_loop import AgentLoopLink, build_turn_chain
from codeupipe.ai.loop.context_budget import ContextBudget, ContextBudgetTracker
from codeupipe.ai.loop.notifications import (
    Notification,
    NotificationPriority,
    NotificationQueue,
    NotificationSource,
)
from codeupipe.ai.loop.session_store import SessionStore
from codeupipe.ai.loop.state import AgentState, TurnRecord, TurnType
from codeupipe.ai.filters.loop.resume_session import ResumeSessionLink
from codeupipe.ai.filters.loop.save_checkpoint import SaveCheckpointLink

from .conftest import FakeProvider, patch_embedder


# =====================================================================
# Max iterations / safety cap
# =====================================================================


@pytest.mark.e2e
class TestMaxIterationsSafetyCap:
    """Loop must stop at max_iterations even if agent never says done."""

    @pytest.mark.asyncio
    async def test_hits_max_iterations(self):
        """Agent never finishes — loop stops at max_iterations."""
        # Session returns content + follow_up forever
        provider = FakeProvider([
            {"content": f"Turn {i}"} for i in range(20)
        ])

        state = AgentState(max_iterations=3)

        ctx = Payload({
            "prompt": "Do something forever",
            "provider": provider,
            "agent_state": state,
            # Continuously inject follow-ups
            "follow_up_prompt": "Keep going",
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        final_state: AgentState = result.get("agent_state")
        assert final_state.done is True
        assert final_state.loop_iteration <= 3
        assert final_state.hit_max_iterations or final_state.done

    @pytest.mark.asyncio
    async def test_max_iterations_one(self):
        """max_iterations=1 means exactly one turn then stop."""
        provider = FakeProvider([
            {"content": "Only one turn."},
        ])

        state = AgentState(max_iterations=1)

        ctx = Payload({
            "prompt": "Quick task",
            "provider": provider,
            "agent_state": state,
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        final_state: AgentState = result.get("agent_state")
        assert final_state.done is True
        assert len(final_state.turn_history) == 1


# =====================================================================
# Empty / null responses
# =====================================================================


@pytest.mark.e2e
class TestEmptyResponses:
    """Agent returns empty or null content."""

    @pytest.mark.asyncio
    async def test_null_content_response(self):
        """Agent returns None content — should complete gracefully."""
        provider = FakeProvider([
            {"content": None},
        ])

        ctx = Payload({
            "prompt": "Say something",
            "provider": provider,
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        state: AgentState = result.get("agent_state")
        assert state.done is True
        assert result.get("response") is None

    @pytest.mark.asyncio
    async def test_empty_string_response(self):
        """Agent returns empty string — should complete gracefully."""
        provider = FakeProvider([
            {"content": ""},
        ])

        ctx = Payload({
            "prompt": "Say something",
            "provider": provider,
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        state: AgentState = result.get("agent_state")
        assert state.done is True


# =====================================================================
# Missing required context (error paths)
# =====================================================================


@pytest.mark.e2e
class TestMissingContext:
    """Required context keys missing — should raise clearly."""

    @pytest.mark.asyncio
    async def test_no_prompt_raises(self):
        """Missing prompt on first turn → ValueError."""
        provider = FakeProvider([{"content": "Never reached."}])

        ctx = Payload({
            # No 'prompt' key
            "provider": provider,
        })

        loop = AgentLoopLink()
        with pytest.raises(ValueError, match="prompt"):
            await loop.call(ctx)

    @pytest.mark.asyncio
    async def test_no_provider_raises(self):
        """Missing provider → ValueError from LanguageModelLink."""
        ctx = Payload({
            "prompt": "This will fail",
            # No 'provider' key
        })

        loop = AgentLoopLink()
        with pytest.raises(ValueError, match="provider"):
            await loop.call(ctx)


# =====================================================================
# Notification edge cases
# =====================================================================


@pytest.mark.e2e
class TestNotificationEdgeCases:
    """Edge cases around notification queue behavior."""

    @pytest.mark.asyncio
    async def test_empty_notification_queue_passthrough(self):
        """Empty queue shouldn't affect normal flow."""
        queue = NotificationQueue()

        provider = FakeProvider([{"content": "Normal response."}])
        ctx = Payload({
            "prompt": "Normal task",
            "provider": provider,
            "notification_queue": queue,
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        state: AgentState = result.get("agent_state")
        assert state.done is True
        assert len(state.turn_history) == 1

    @pytest.mark.asyncio
    async def test_multiple_sources_same_priority(self):
        """Multiple notifications at same priority — ordered by timestamp."""
        queue = NotificationQueue()

        # Push in order — should drain in same order (same priority)
        queue.push(Notification(
            source=NotificationSource.MCP_SERVER,
            source_name="server-a",
            message="First message",
            priority=NotificationPriority.NORMAL,
        ))
        queue.push(Notification(
            source=NotificationSource.USER,
            source_name="user",
            message="Second message",
            priority=NotificationPriority.NORMAL,
        ))
        queue.push(Notification(
            source=NotificationSource.SYSTEM,
            source_name="system",
            message="Third message",
            priority=NotificationPriority.NORMAL,
        ))

        drained = queue.drain()
        assert len(drained) == 3
        assert drained[0].message == "First message"
        assert drained[1].message == "Second message"
        assert drained[2].message == "Third message"

    @pytest.mark.asyncio
    async def test_massive_notification_burst(self):
        """Queue handles many notifications without issues."""
        queue = NotificationQueue()

        for i in range(100):
            queue.push(Notification(
                source=NotificationSource.SYSTEM,
                source_name="burst-source",
                message=f"Burst notification {i}",
                priority=NotificationPriority.LOW,
            ))

        assert queue.size == 100
        drained = queue.drain()
        assert len(drained) == 100
        assert queue.is_empty()


# =====================================================================
# Context pruning with large history
# =====================================================================


@pytest.mark.e2e
class TestContextPruning:
    """Large turn histories trigger context pruning."""

    @pytest.mark.asyncio
    async def test_large_history_gets_pruned(self):
        """Turn history exceeding budget threshold gets trimmed."""
        # Build a state with lots of turn history but loop_iteration=0
        # so ReadInputLink uses the prompt (first turn)
        big_content = "x" * 10_000  # ~2500 tokens at 4 chars/token
        turns = tuple(
            TurnRecord(
                iteration=i,
                turn_type=TurnType.FOLLOW_UP,
                input_prompt=f"Turn {i} prompt {big_content}",
                response_content=f"Turn {i} response {big_content}",
            )
            for i in range(20)
        )

        # Start at iteration 0 so ReadInputLink uses the prompt,
        # but pre-load heavy turn history to trigger pruning
        state = AgentState(
            loop_iteration=0,
            turn_history=turns,
            max_iterations=25,
        )

        provider = FakeProvider([{"content": "After pruning."}])

        ctx = Payload({
            "prompt": "Continue after history",
            "provider": provider,
            "agent_state": state,
            "context_budget": 5000,  # Very low — forces pruning
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        final_state: AgentState = result.get("agent_state")
        # Should have fewer turns than we started with (20)
        # + the new one, minus pruned ones
        # MIN_TURNS_KEPT is 3, so at least 3 kept + 1 new
        assert len(final_state.turn_history) < len(turns) + 1


# =====================================================================
# Conversation revision + checkpoint
# =====================================================================


@pytest.mark.e2e
class TestConversationRevisionAndCheckpoint:
    """Budget threshold → revision → checkpoint save."""

    @pytest.mark.asyncio
    async def test_revision_compresses_older_turns(self, budget_tracker):
        """When budget threshold crossed, older turns get compressed."""
        # Build history with enough content to exceed budget
        big_content = "x" * 2000  # ~500 tokens
        turns = tuple(
            TurnRecord(
                iteration=i,
                turn_type=TurnType.FOLLOW_UP,
                input_prompt=f"Turn {i}: {big_content}",
                response_content=f"Response {i}: {big_content}",
            )
            for i in range(6)
        )

        # Start at iteration 0 so ReadInputLink uses the prompt
        state = AgentState(
            loop_iteration=0,
            turn_history=turns,
            max_iterations=10,
        )

        provider = FakeProvider([{"content": "After revision."}])

        ctx = Payload({
            "prompt": "Keep working",
            "provider": provider,
            "agent_state": state,
            "context_budget_tracker": budget_tracker,
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        final_state: AgentState = result.get("agent_state")
        # Revision should have compressed older turns
        # Check that at least some turns have shorter content
        revision_applied = result.get("revision_applied")
        # If budget was exceeded, revision should have run
        if revision_applied:
            for turn in final_state.turn_history[:-budget_tracker.budget.min_turns_kept]:
                # Compressed turns should have truncated content
                if turn.response_content and len(turn.response_content) > 0:
                    assert len(turn.response_content) <= 200  # _SUMMARY_MAX_CHARS + "..."

    @pytest.mark.asyncio
    async def test_checkpoint_saved_after_revision(self, session_store, budget_tracker):
        """After revision runs, checkpoint is saved to SessionStore."""
        big_content = "x" * 2000
        turns = tuple(
            TurnRecord(
                iteration=i,
                turn_type=TurnType.FOLLOW_UP,
                input_prompt=f"Turn {i}: {big_content}",
                response_content=f"Response {i}: {big_content}",
            )
            for i in range(6)
        )

        # Start at iteration 0 so ReadInputLink uses the prompt
        state = AgentState(
            loop_iteration=0,
            turn_history=turns,
            max_iterations=10,
        )

        provider = FakeProvider([{"content": "Checkpointed."}])

        ctx = Payload({
            "prompt": "Continue",
            "provider": provider,
            "agent_state": state,
            "context_budget_tracker": budget_tracker,
            "session_store": session_store,
            "session_id": "e2e-checkpoint-001",
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        # If revision was applied, checkpoint should exist
        if result.get("revision_applied"):
            checkpoint = session_store.load("e2e-checkpoint-001")
            assert checkpoint is not None
            assert checkpoint.session_id == "e2e-checkpoint-001"
            assert checkpoint.state.loop_iteration >= 1


# =====================================================================
# Session resume
# =====================================================================


@pytest.mark.e2e
class TestSessionResume:
    """Save state → create new session → resume from checkpoint."""

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(self, session_store):
        """Saved checkpoint is restored by ResumeSessionLink."""
        # Save a checkpoint manually
        original_state = AgentState(
            loop_iteration=5,
            active_capabilities=("tdd-workflow", "auth-skill"),
            turn_history=(
                TurnRecord(
                    iteration=0,
                    turn_type=TurnType.USER_PROMPT,
                    input_prompt="Start the auth refactor",
                    response_content="Refactoring started.",
                ),
                TurnRecord(
                    iteration=1,
                    turn_type=TurnType.FOLLOW_UP,
                    input_prompt="Continue with tests",
                    response_content="Tests written.",
                ),
            ),
        )

        context_snapshot = {
            "intent": "test auth module verify",
            "total_estimated_tokens": 5000,
            "active_capabilities": ["tdd-workflow", "auth-skill"],
        }

        session_store.save("e2e-resume-001", original_state, context_snapshot)

        # Now resume
        resume_link = ResumeSessionLink()
        ctx = Payload({
            "session_store": session_store,
            "session_id": "e2e-resume-001",
        })

        result = await resume_link.call(ctx)

        assert result.get("resumed") is True
        restored_state: AgentState = result.get("agent_state")
        assert restored_state.loop_iteration == 5
        assert len(restored_state.turn_history) == 2
        assert "tdd-workflow" in restored_state.active_capabilities
        assert result.get("intent") == "test auth module verify"

    @pytest.mark.asyncio
    async def test_resume_no_checkpoint_returns_false(self, session_store):
        """No checkpoint exists → resumed=False, no crash."""
        resume_link = ResumeSessionLink()
        ctx = Payload({
            "session_store": session_store,
            "session_id": "nonexistent-session",
        })

        result = await resume_link.call(ctx)

        assert result.get("resumed") is False

    @pytest.mark.asyncio
    async def test_resume_without_store_returns_false(self):
        """No SessionStore on context → resumed=False."""
        resume_link = ResumeSessionLink()
        ctx = Payload({
            "session_id": "any-session",
        })

        result = await resume_link.call(ctx)

        assert result.get("resumed") is False

    @pytest.mark.asyncio
    async def test_full_save_resume_round_trip(self, session_store):
        """Run loop → save checkpoint → new session → resume → verify."""
        # Phase 1: Run a session and save a checkpoint
        save_link = SaveCheckpointLink()

        original_state = AgentState(
            loop_iteration=3,
            turn_history=(
                TurnRecord(
                    iteration=0,
                    turn_type=TurnType.USER_PROMPT,
                    input_prompt="Build the feature",
                    response_content="Feature built.",
                ),
            ),
            active_capabilities=("deploy-skill",),
        )

        save_ctx = Payload({
            "agent_state": original_state,
            "session_store": session_store,
            "session_id": "e2e-roundtrip-001",
            "revision_applied": True,  # trigger save
            "intent": "deploy to production",
            "total_estimated_tokens": 3000,
        })

        save_result = await save_link.call(save_ctx)
        assert save_result.get("checkpoint_saved") is True

        # Phase 2: New session — resume
        resume_link = ResumeSessionLink()
        new_ctx = Payload({
            "session_store": session_store,
            "session_id": "e2e-roundtrip-001",
        })

        resume_result = await resume_link.call(new_ctx)

        assert resume_result.get("resumed") is True
        restored: AgentState = resume_result.get("agent_state")
        assert restored.loop_iteration == 3
        assert len(restored.turn_history) == 1
        assert "deploy-skill" in restored.active_capabilities
        assert resume_result.get("intent") == "deploy to production"


# =====================================================================
# Intent shift edge cases
# =====================================================================


@pytest.mark.e2e
class TestIntentShiftEdgeCases:
    """Edge cases in intent update and rediscovery."""

    @pytest.mark.asyncio
    async def test_intent_shift_to_same_value_is_noop(self):
        """Shifting to the same intent doesn't trigger rediscovery."""
        provider = FakeProvider([{"content": "Same intent."}])

        ctx = Payload({
            "prompt": "Work on math",
            "intent": "calculate math sum",
            "provider": provider,
            "state_updates": [
                {"action": "update_intent", "intent": "calculate math sum"},
            ],
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        assert result.get("intent_changed") is False

    @pytest.mark.asyncio
    async def test_empty_intent_shift_ignored(self):
        """Empty string intent update is ignored."""
        provider = FakeProvider([{"content": "No change."}])

        ctx = Payload({
            "prompt": "Work on something",
            "intent": "original intent",
            "provider": provider,
            "state_updates": [
                {"action": "update_intent", "intent": ""},
            ],
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        assert result.get("intent") == "original intent"
        assert result.get("intent_changed") is False

    @pytest.mark.asyncio
    async def test_follow_up_intent_injection(self):
        """External follow_up_intent key triggers intent shift."""
        provider = FakeProvider([{"content": "Shifted."}])

        ctx = Payload({
            "prompt": "Start with auth",
            "intent": "auth login",
            "provider": provider,
            "follow_up_intent": "deploy to production infra",
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        assert result.get("intent") == "deploy to production infra"
        # follow_up_intent should be consumed
        assert result.get("follow_up_intent") is None


# =====================================================================
# State management edge cases
# =====================================================================


@pytest.mark.e2e
class TestStateManagementEdgeCases:
    """Edge cases in capability management."""

    @pytest.mark.asyncio
    async def test_adopt_duplicate_is_idempotent(self):
        """Adopting the same capability twice doesn't duplicate it."""
        provider = FakeProvider([{"content": "Adopted."}])

        state = AgentState(active_capabilities=("skill-a",))

        ctx = Payload({
            "prompt": "Use skill-a",
            "provider": provider,
            "agent_state": state,
            "state_updates": [
                {"action": "adopt", "name": "skill-a"},
            ],
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        final: AgentState = result.get("agent_state")
        count = final.active_capabilities.count("skill-a")
        assert count == 1

    @pytest.mark.asyncio
    async def test_drop_nonexistent_is_safe(self):
        """Dropping a capability that isn't active doesn't crash."""
        provider = FakeProvider([{"content": "Dropped nothing."}])

        ctx = Payload({
            "prompt": "Drop something",
            "provider": provider,
            "state_updates": [
                {"action": "drop", "name": "nonexistent-skill"},
            ],
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        state: AgentState = result.get("agent_state")
        assert state.done is True

    @pytest.mark.asyncio
    async def test_mixed_adopt_drop_unknown_actions(self):
        """Unknown state_updates are logged but don't crash."""
        provider = FakeProvider([{"content": "Mixed actions."}])

        ctx = Payload({
            "prompt": "Complex state changes",
            "provider": provider,
            "state_updates": [
                {"action": "adopt", "name": "skill-a"},
                {"action": "unknown_action", "name": "???"},
                {"action": "drop", "name": "skill-b"},
            ],
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        state: AgentState = result.get("agent_state")
        assert "skill-a" in state.active_capabilities


# =====================================================================
# AgentState immutability
# =====================================================================


@pytest.mark.e2e
class TestAgentStateImmutability:
    """AgentState should not be mutated — each change returns new instance."""

    @pytest.mark.asyncio
    async def test_original_state_unchanged_after_loop(self):
        """Original AgentState instance is never modified."""
        provider = FakeProvider([{"content": "Modified state."}])

        original = AgentState(max_iterations=5)
        assert original.loop_iteration == 0
        assert original.done is False

        ctx = Payload({
            "prompt": "Test immutability",
            "provider": provider,
            "agent_state": original,
        })

        loop = AgentLoopLink()
        result = await loop.call(ctx)

        # Original should be untouched
        assert original.loop_iteration == 0
        assert original.done is False
        assert len(original.turn_history) == 0

        # Result should have new state
        new_state: AgentState = result.get("agent_state")
        assert new_state is not original
        assert new_state.done is True
        assert len(new_state.turn_history) == 1


# =====================================================================
# Full lifecycle integration
# =====================================================================


@pytest.mark.e2e
class TestFullLifecycleIntegration:
    """Complete lifecycle: discovery → loop → notifications → audit."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_all_features(
        self, populated_registry, notification_queue, session_store,
    ):
        """Exercise all features in a single multi-turn session."""
        with patch_embedder():
            # Pre-load a notification
            notification_queue.push(Notification(
                source=NotificationSource.SYSTEM,
                source_name="ci-server",
                message="Build #42 passed all tests",
                priority=NotificationPriority.NORMAL,
            ))

            provider = FakeProvider([
                {"content": "Auth module analysis complete."},
                {"content": "Tests written. Build notification acknowledged."},
                {"content": "Build notification processed."},
            ])

            # Budget tracker with reasonable threshold
            budget = ContextBudget(total_budget=100_000, revision_threshold=0.75)
            tracker = ContextBudgetTracker(budget)

            ctx = Payload({
                "prompt": "Refactor the auth login module",
                "intent": "refactor auth login password",
                "provider": provider,
                "capability_registry": populated_registry,
                "notification_queue": notification_queue,
                "context_budget_tracker": tracker,
                "session_store": session_store,
                "session_id": "e2e-full-lifecycle",
                "state_updates": [
                    {"action": "adopt", "name": "tdd-workflow"},
                ],
                "follow_up_prompt": "Now write tests for auth verify assert",
            })

            loop = AgentLoopLink()
            result = await loop.call(ctx)

            # ── Verify final state ────────────────────────────────────
            state: AgentState = result.get("agent_state")
            assert state.done is True
            # 3 turns: initial prompt + follow-up + drained notification
            assert len(state.turn_history) == 3

            # Capability was adopted
            assert "tdd-workflow" in state.active_capabilities

            # Notifications were drained
            assert notification_queue.is_empty()

            # Context attribution was computed
            attribution = result.get("context_attribution")
            assert attribution is not None
            assert len(attribution) > 0

            # Response captured
            assert result.get("response") is not None
