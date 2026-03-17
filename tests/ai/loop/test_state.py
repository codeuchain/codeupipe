"""RED PHASE — Tests for AgentState and TurnRecord.

AgentState is the persistent state across loop iterations.
Frozen dataclass — every mutation returns a new instance.
"""

from datetime import datetime, timezone

import pytest

from codeupipe.ai.loop.state import AgentState, TurnRecord, TurnType


@pytest.mark.unit
class TestTurnRecord:
    """Unit tests for TurnRecord (immutable turn history entry)."""

    def test_create_with_defaults(self):
        """TurnRecord can be created with minimal args."""
        turn = TurnRecord(
            iteration=0,
            turn_type=TurnType.USER_PROMPT,
            input_prompt="hello",
        )
        assert turn.iteration == 0
        assert turn.turn_type == TurnType.USER_PROMPT
        assert turn.input_prompt == "hello"
        assert turn.response_content is None
        assert turn.tool_calls_count == 0
        assert isinstance(turn.timestamp, datetime)

    def test_create_with_all_fields(self):
        """TurnRecord stores response content and tool count."""
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        turn = TurnRecord(
            iteration=2,
            turn_type=TurnType.FOLLOW_UP,
            input_prompt="continue",
            response_content="Done!",
            tool_calls_count=3,
            timestamp=ts,
        )
        assert turn.response_content == "Done!"
        assert turn.tool_calls_count == 3
        assert turn.timestamp == ts

    def test_is_frozen(self):
        """TurnRecord is immutable."""
        turn = TurnRecord(
            iteration=0,
            turn_type=TurnType.USER_PROMPT,
            input_prompt="hi",
        )
        with pytest.raises(AttributeError):
            turn.iteration = 5  # type: ignore


@pytest.mark.unit
class TestTurnType:
    """Unit tests for TurnType enum."""

    def test_values(self):
        """All expected turn types exist."""
        assert TurnType.USER_PROMPT == "user_prompt"
        assert TurnType.FOLLOW_UP == "follow_up"
        assert TurnType.NOTIFICATION == "notification"


@pytest.mark.unit
class TestAgentState:
    """Unit tests for AgentState (frozen, immutable state)."""

    def test_default_state(self):
        """Default state is iteration 0, not done, max 10."""
        state = AgentState()
        assert state.loop_iteration == 0
        assert state.done is False
        assert state.max_iterations == 10
        assert state.turn_history == ()
        assert state.active_capabilities == ()

    def test_custom_max_iterations(self):
        """Max iterations can be set at creation."""
        state = AgentState(max_iterations=3)
        assert state.max_iterations == 3

    def test_is_frozen(self):
        """AgentState is immutable."""
        state = AgentState()
        with pytest.raises(AttributeError):
            state.done = True  # type: ignore

    # ── Mutations ─────────────────────────────────────────────────────

    def test_increment(self):
        """increment() advances loop_iteration by 1."""
        state = AgentState()
        next_state = state.increment()
        assert next_state.loop_iteration == 1
        assert state.loop_iteration == 0  # original unchanged

    def test_increment_preserves_fields(self):
        """increment() preserves all other fields."""
        state = AgentState(max_iterations=5, active_capabilities=("tool_a",))
        next_state = state.increment()
        assert next_state.max_iterations == 5
        assert next_state.active_capabilities == ("tool_a",)

    def test_mark_done(self):
        """mark_done() sets done=True."""
        state = AgentState()
        done_state = state.mark_done()
        assert done_state.done is True
        assert state.done is False  # original unchanged

    def test_record_turn(self):
        """record_turn() appends a TurnRecord to history."""
        state = AgentState()
        turn = TurnRecord(
            iteration=0,
            turn_type=TurnType.USER_PROMPT,
            input_prompt="hello",
            response_content="Hi!",
        )
        next_state = state.record_turn(turn)
        assert len(next_state.turn_history) == 1
        assert next_state.turn_history[0] is turn
        assert len(state.turn_history) == 0  # original unchanged

    def test_record_multiple_turns(self):
        """Multiple turns form an ordered history."""
        state = AgentState()
        t1 = TurnRecord(iteration=0, turn_type=TurnType.USER_PROMPT, input_prompt="a")
        t2 = TurnRecord(iteration=1, turn_type=TurnType.FOLLOW_UP, input_prompt="b")
        state = state.record_turn(t1).record_turn(t2)
        assert len(state.turn_history) == 2
        assert state.turn_history[0].input_prompt == "a"
        assert state.turn_history[1].input_prompt == "b"

    def test_add_capability(self):
        """add_capability() tracks an adopted capability."""
        state = AgentState()
        next_state = state.add_capability("file_reader")
        assert "file_reader" in next_state.active_capabilities
        assert len(state.active_capabilities) == 0

    def test_add_capability_deduplicates(self):
        """Adding the same capability twice doesn't duplicate."""
        state = AgentState().add_capability("x")
        state = state.add_capability("x")
        assert state.active_capabilities == ("x",)

    def test_remove_capability(self):
        """remove_capability() drops a tracked capability."""
        state = AgentState().add_capability("a").add_capability("b")
        state = state.remove_capability("a")
        assert state.active_capabilities == ("b",)

    def test_remove_missing_capability(self):
        """Removing a non-existent capability is a no-op."""
        state = AgentState()
        next_state = state.remove_capability("missing")
        assert next_state.active_capabilities == ()

    # ── Queries ───────────────────────────────────────────────────────

    def test_should_continue_true_when_fresh(self):
        """Fresh state should continue."""
        assert AgentState().should_continue is True

    def test_should_continue_false_when_done(self):
        """Done state should not continue."""
        assert AgentState().mark_done().should_continue is False

    def test_should_continue_false_at_max(self):
        """State at max iterations should not continue."""
        state = AgentState(loop_iteration=10, max_iterations=10)
        assert state.should_continue is False

    def test_is_first_turn(self):
        """is_first_turn is True at iteration 0."""
        assert AgentState().is_first_turn is True
        assert AgentState(loop_iteration=1).is_first_turn is False

    def test_hit_max_iterations(self):
        """hit_max_iterations when stopped by cap, not by done signal."""
        # At max but not done → hit max
        state = AgentState(loop_iteration=10, max_iterations=10)
        assert state.hit_max_iterations is True

        # Done before max → did not hit max
        state = AgentState(loop_iteration=5, max_iterations=10, done=True)
        assert state.hit_max_iterations is False
