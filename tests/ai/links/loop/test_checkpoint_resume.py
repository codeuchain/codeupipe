"""Tests for SaveCheckpointLink and ResumeSessionLink."""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.save_checkpoint import SaveCheckpointLink
from codeupipe.ai.filters.loop.resume_session import ResumeSessionLink
from codeupipe.ai.loop.session_store import SessionStore
from codeupipe.ai.loop.state import AgentState, TurnRecord, TurnType


def _make_state(iteration: int = 3) -> AgentState:
    turns = tuple(
        TurnRecord(
            iteration=i,
            turn_type=TurnType.USER_PROMPT,
            input_prompt=f"prompt {i}",
            response_content=f"response {i}",
        )
        for i in range(iteration)
    )
    return AgentState(
        loop_iteration=iteration,
        turn_history=turns,
        active_capabilities=("tool_a",),
    )


@pytest.mark.unit
class TestSaveCheckpointLink:
    """Unit tests for SaveCheckpointLink."""

    @pytest.mark.asyncio
    async def test_saves_after_revision(self):
        """Checkpoint saved when revision_applied=True."""
        link = SaveCheckpointLink()
        store = SessionStore(":memory:")
        state = _make_state()

        ctx = Payload({
            "revision_applied": True,
            "session_store": store,
            "agent_state": state,
            "session_id": "s1",
            "intent": "build auth",
            "total_estimated_tokens": 5000,
        })

        result = await link.call(ctx)

        assert result.get("checkpoint_saved") is True
        checkpoint = store.load("s1")
        assert checkpoint is not None
        assert checkpoint.state.loop_iteration == 3

    @pytest.mark.asyncio
    async def test_skip_no_revision(self):
        """No save when revision_applied=False."""
        link = SaveCheckpointLink()
        store = SessionStore(":memory:")

        ctx = Payload({
            "revision_applied": False,
            "session_store": store,
            "agent_state": _make_state(),
            "session_id": "s1",
        })

        result = await link.call(ctx)

        assert result.get("checkpoint_saved") is False
        assert store.load("s1") is None

    @pytest.mark.asyncio
    async def test_skip_no_store(self):
        """No save when session_store missing."""
        link = SaveCheckpointLink()

        ctx = Payload({
            "revision_applied": True,
            "agent_state": _make_state(),
            "session_id": "s1",
        })

        result = await link.call(ctx)

        assert result.get("checkpoint_saved") is False

    @pytest.mark.asyncio
    async def test_skip_no_session_id(self):
        """No save when session_id missing."""
        link = SaveCheckpointLink()
        store = SessionStore(":memory:")

        ctx = Payload({
            "revision_applied": True,
            "session_store": store,
            "agent_state": _make_state(),
        })

        result = await link.call(ctx)

        assert result.get("checkpoint_saved") is False

    @pytest.mark.asyncio
    async def test_context_snapshot_includes_metadata(self):
        """Checkpoint includes intent and token count."""
        link = SaveCheckpointLink()
        store = SessionStore(":memory:")

        ctx = Payload({
            "revision_applied": True,
            "session_store": store,
            "agent_state": _make_state(),
            "session_id": "s1",
            "intent": "write tests",
            "total_estimated_tokens": 42000,
        })

        await link.call(ctx)

        checkpoint = store.load("s1")
        assert checkpoint.context_snapshot["intent"] == "write tests"
        assert checkpoint.context_snapshot["total_estimated_tokens"] == 42000


@pytest.mark.unit
class TestResumeSessionLink:
    """Unit tests for ResumeSessionLink."""

    @pytest.mark.asyncio
    async def test_resume_existing_session(self):
        """Restores state from checkpoint."""
        store = SessionStore(":memory:")
        state = _make_state(5)
        store.save("s1", state, {"intent": "build auth"})

        link = ResumeSessionLink()
        ctx = Payload({
            "session_store": store,
            "session_id": "s1",
        })

        result = await link.call(ctx)

        assert result.get("resumed") is True
        restored = result.get("agent_state")
        assert restored.loop_iteration == 5
        assert len(restored.turn_history) == 5
        assert result.get("intent") == "build auth"

    @pytest.mark.asyncio
    async def test_no_checkpoint_found(self):
        """No checkpoint — resumed=False."""
        store = SessionStore(":memory:")
        link = ResumeSessionLink()

        ctx = Payload({
            "session_store": store,
            "session_id": "unknown",
        })

        result = await link.call(ctx)

        assert result.get("resumed") is False

    @pytest.mark.asyncio
    async def test_no_store(self):
        """No store — resumed=False."""
        link = ResumeSessionLink()
        ctx = Payload({"session_id": "s1"})

        result = await link.call(ctx)

        assert result.get("resumed") is False

    @pytest.mark.asyncio
    async def test_no_session_id(self):
        """No session_id — resumed=False."""
        link = ResumeSessionLink()
        store = SessionStore(":memory:")
        ctx = Payload({"session_store": store})

        result = await link.call(ctx)

        assert result.get("resumed") is False

    @pytest.mark.asyncio
    async def test_preserves_existing_context(self):
        """Resume doesn't clobber non-checkpoint keys."""
        store = SessionStore(":memory:")
        store.save("s1", _make_state(), {"intent": "restored"})

        link = ResumeSessionLink()
        ctx = Payload({
            "session_store": store,
            "session_id": "s1",
            "keep_this": "value",
        })

        result = await link.call(ctx)

        assert result.get("keep_this") == "value"
        assert result.get("resumed") is True
