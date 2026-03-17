"""Tests for SessionStore — SQLite-backed session persistence."""

import pytest
from datetime import datetime, timezone

from codeupipe.ai.loop.session_store import SessionStore
from codeupipe.ai.loop.state import AgentState, TurnRecord, TurnType


def _make_state(iteration: int = 3, num_turns: int = 2) -> AgentState:
    """Factory for test AgentState."""
    turns = tuple(
        TurnRecord(
            iteration=i,
            turn_type=TurnType.USER_PROMPT,
            input_prompt=f"prompt {i}",
            response_content=f"response {i}",
            tool_calls_count=1,
        )
        for i in range(num_turns)
    )
    return AgentState(
        loop_iteration=iteration,
        done=False,
        max_iterations=10,
        turn_history=turns,
        active_capabilities=("tool_a", "tool_b"),
    )


@pytest.mark.unit
class TestSessionStore:
    """Unit tests for SessionStore."""

    def test_save_and_load(self):
        """Round-trip: save then load restores state."""
        store = SessionStore(":memory:")
        state = _make_state()

        store.save("session-1", state, {"intent": "build auth"})
        checkpoint = store.load("session-1")

        assert checkpoint is not None
        assert checkpoint.session_id == "session-1"
        assert checkpoint.state.loop_iteration == 3
        assert len(checkpoint.state.turn_history) == 2
        assert checkpoint.state.active_capabilities == ("tool_a", "tool_b")
        assert checkpoint.context_snapshot["intent"] == "build auth"

    def test_load_nonexistent(self):
        """Load returns None for unknown session."""
        store = SessionStore(":memory:")
        assert store.load("unknown") is None

    def test_load_latest_checkpoint(self):
        """Multiple saves — load returns the most recent."""
        store = SessionStore(":memory:")
        state1 = _make_state(iteration=1)
        state2 = _make_state(iteration=5)

        store.save("s1", state1, {"step": 1})
        store.save("s1", state2, {"step": 2})

        checkpoint = store.load("s1")
        assert checkpoint.state.loop_iteration == 5
        assert checkpoint.context_snapshot["step"] == 2

    def test_list_sessions(self):
        """Lists distinct session IDs."""
        store = SessionStore(":memory:")
        store.save("s1", _make_state())
        store.save("s2", _make_state())
        store.save("s1", _make_state())

        sessions = store.list_sessions()
        assert sorted(sessions) == ["s1", "s2"]

    def test_delete(self):
        """Delete removes all checkpoints for a session."""
        store = SessionStore(":memory:")
        store.save("s1", _make_state())
        store.save("s1", _make_state())
        store.save("s2", _make_state())

        deleted = store.delete("s1")
        assert deleted == 2
        assert store.load("s1") is None
        assert store.load("s2") is not None

    def test_turn_history_serialization(self):
        """Turn history round-trips: types, content, timestamps."""
        store = SessionStore(":memory:")
        state = _make_state(num_turns=3)

        store.save("s1", state)
        checkpoint = store.load("s1")

        assert len(checkpoint.state.turn_history) == 3
        for i, turn in enumerate(checkpoint.state.turn_history):
            assert turn.iteration == i
            assert turn.turn_type == TurnType.USER_PROMPT
            assert turn.input_prompt == f"prompt {i}"
            assert turn.response_content == f"response {i}"
            assert turn.tool_calls_count == 1

    def test_done_state_preserved(self):
        """Done flag serializes correctly."""
        store = SessionStore(":memory:")
        state = _make_state().mark_done()

        store.save("s1", state)
        checkpoint = store.load("s1")

        assert checkpoint.state.done is True

    def test_empty_context_snapshot(self):
        """None context_snapshot serializes as empty dict."""
        store = SessionStore(":memory:")
        store.save("s1", _make_state(), None)

        checkpoint = store.load("s1")
        assert checkpoint.context_snapshot == {}
