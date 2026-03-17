"""Unit tests for codeupipe.ai.eval.collector — mass data capture."""

import asyncio

import pytest

from codeupipe.ai.eval.collector import EvalCollector
from codeupipe.ai.eval.storage import EvalStore
from codeupipe.ai.eval.types import (
    RunConfig,
    RunOutcome,
    ToolCallRecord,
    TurnSnapshot,
)


@pytest.fixture
def store(tmp_path):
    s = EvalStore(tmp_path / "collector_test.db")
    yield s
    s.close()


@pytest.fixture
def collector(store):
    return EvalCollector(store)


@pytest.mark.unit
class TestCollectorLifecycle:
    """Tests for begin_run / end_run lifecycle."""

    def test_begin_run(self, collector):
        run_id = collector.begin_run(config=RunConfig(model="gpt-4.1"))
        assert run_id
        assert collector.is_active
        assert collector.run_id == run_id

    def test_end_run(self, collector):
        collector.begin_run()
        run = collector.end_run(RunOutcome.SUCCESS)

        assert not collector.is_active
        assert run.outcome == RunOutcome.SUCCESS
        assert run.run_id

    def test_end_without_begin_raises(self, collector):
        with pytest.raises(RuntimeError):
            collector.end_run()

    def test_custom_run_id(self, collector):
        collector.begin_run(run_id="custom_123")
        assert collector.run_id == "custom_123"

    def test_session_and_scenario(self, collector):
        collector.begin_run(
            session_id="sess_99",
            scenario_id="sc_42",
            experiment_id="exp_7",
        )
        run = collector.end_run()

        assert run.session_id == "sess_99"
        assert run.scenario_id == "sc_42"
        assert run.experiment_id == "exp_7"


@pytest.mark.unit
class TestCollectorRecording:
    """Tests for turn, tool call, and raw recording."""

    def test_record_turn(self, collector, store):
        collector.begin_run()
        collector.record_turn(TurnSnapshot(
            iteration=0,
            turn_type="user_prompt",
            input_prompt="hello world",
        ))

        run = collector.end_run()
        assert len(run.turns) == 1
        assert run.turns[0].input_prompt == "hello world"

    def test_record_multiple_turns(self, collector):
        collector.begin_run()
        for i in range(5):
            collector.record_turn(TurnSnapshot(
                iteration=i,
                turn_type="follow_up",
                input_prompt=f"turn {i}",
            ))

        run = collector.end_run()
        assert len(run.turns) == 5

    def test_record_tool_call(self, collector):
        collector.begin_run()
        collector.record_tool_call(ToolCallRecord(
            iteration=1,
            tool_name="file_write",
            server_name="fs-server",
        ))

        run = collector.end_run()
        assert len(run.tool_calls) == 1
        assert run.tool_calls[0].tool_name == "file_write"

    def test_record_raw_event(self, collector, store):
        collector.begin_run()
        collector.record_raw("notification", {"type": "server_added", "server": "new-server"})

        run = collector.end_run()

        # Raw events should be in the store
        events = store.get_raw_events(run_id=run.run_id, event_type="notification")
        assert len(events) == 1
        assert events[0].payload["server"] == "new-server"

    def test_increment_counter(self, collector):
        collector.begin_run()
        collector.increment("intent_shifts")
        collector.increment("intent_shifts")
        collector.increment("intent_shifts", 3)

        run = collector.end_run()
        assert run.raw_data["intent_shifts"] == 5

    def test_set_raw(self, collector):
        collector.begin_run()
        collector.set_raw("custom_key", {"nested": True})

        run = collector.end_run()
        assert run.raw_data["custom_key"]["nested"] is True

    def test_inactive_recording_ignored(self, collector):
        # No active run — recording should be silently ignored
        collector.record_turn(TurnSnapshot(
            iteration=0, turn_type="user_prompt", input_prompt="ignored",
        ))
        collector.record_tool_call(ToolCallRecord(
            iteration=0, tool_name="ignored",
        ))
        collector.record_raw("ignored", {})
        collector.increment("ignored")
        collector.set_raw("ignored", True)
        # No error raised


@pytest.mark.unit
class TestCollectorMetrics:
    """Tests for automatic metric computation on end_run."""

    def test_metrics_computed(self, collector):
        collector.begin_run(config=RunConfig(model="gpt-4.1"))
        for i in range(3):
            collector.record_turn(TurnSnapshot(
                iteration=i,
                turn_type="follow_up",
                input_prompt="test",
                tokens_estimated=100,
            ))

        run = collector.end_run(RunOutcome.SUCCESS)
        names = {m.name for m in run.metrics}
        assert "turns_total" in names
        assert "tokens_total" in names
        assert "done_naturally" in names

    def test_metrics_values_correct(self, collector):
        collector.begin_run()
        for i in range(4):
            collector.record_turn(TurnSnapshot(
                iteration=i, turn_type="follow_up", input_prompt="x",
            ))

        run = collector.end_run()
        md = {m.name: m.value for m in run.metrics}
        assert md["turns_total"] == 4.0


@pytest.mark.unit
class TestCollectorPersistence:
    """Tests that data reaches the store."""

    def test_run_persisted(self, collector, store):
        collector.begin_run(run_id="persist_test")
        collector.record_turn(TurnSnapshot(
            iteration=0, turn_type="user_prompt", input_prompt="persist",
        ))
        collector.end_run(RunOutcome.SUCCESS)

        loaded = store.get_run("persist_test")
        assert loaded is not None
        assert loaded.outcome == RunOutcome.SUCCESS
        assert len(loaded.turns) == 1

    def test_raw_events_persisted(self, collector, store):
        collector.begin_run(run_id="raw_persist")
        collector.record_turn(TurnSnapshot(
            iteration=0, turn_type="user_prompt", input_prompt="test",
        ))
        collector.end_run()

        # Each turn recording also saves a raw event
        count = store.count_raw_events(run_id="raw_persist")
        assert count >= 1


@pytest.mark.unit
class TestCollectorAuditProducer:
    """Tests for AuditProducer duck-typing interface."""

    @pytest.mark.asyncio
    async def test_send(self, collector):
        collector.begin_run()

        class FakeEvent:
            def to_dict(self):
                return {"link": "TestLink", "ok": True}

        await collector.send(FakeEvent())

        run = collector.end_run()
        assert len(run.audit_events) == 1
        assert run.audit_events[0]["link"] == "TestLink"

    @pytest.mark.asyncio
    async def test_send_inactive_ignored(self, collector):
        """Send on inactive collector should not raise."""
        class FakeEvent:
            def to_dict(self):
                return {"test": True}

        await collector.send(FakeEvent())  # no error

    @pytest.mark.asyncio
    async def test_flush_noop(self, collector):
        await collector.flush()

    @pytest.mark.asyncio
    async def test_close_noop(self, collector):
        await collector.close()


@pytest.mark.unit
class TestCollectorAgentEvent:
    """Tests for SDK AgentEvent recording."""

    def test_response_event(self, collector):
        collector.begin_run()

        class FakeEvent:
            type = "response"
            iteration = 0
            data = {
                "turn_type": "user_prompt",
                "input_prompt": "hello",
                "content": "world",
                "tool_calls_count": 0,
                "tokens_estimated": 50,
                "model": "gpt-4.1",
            }
            def to_dict(self):
                return {"type": self.type, "data": self.data, "iteration": self.iteration}

        collector.record_agent_event(FakeEvent())

        run = collector.end_run()
        assert len(run.turns) == 1
        assert run.turns[0].input_prompt == "hello"
        assert run.turns[0].response_content == "world"

    def test_tool_call_event(self, collector):
        collector.begin_run()

        class FakeToolEvent:
            type = "tool_call"
            iteration = 1
            data = {"tool_name": "echo", "server_name": "echo-server", "arguments": {"msg": "hi"}}
            def to_dict(self):
                return {"type": self.type, "data": self.data, "iteration": self.iteration}

        collector.record_agent_event(FakeToolEvent())

        run = collector.end_run()
        assert len(run.tool_calls) == 1
        assert run.tool_calls[0].tool_name == "echo"

    def test_notification_event(self, collector):
        collector.begin_run()

        class FakeNotif:
            type = "notification"
            iteration = 0
            data = {"source": "server", "message": "new tool"}
            def to_dict(self):
                return {"type": self.type, "data": self.data}

        collector.record_agent_event(FakeNotif())

        run = collector.end_run()
        assert run.raw_data["notifications_received"] == 1

    def test_state_change_intent_shift(self, collector):
        collector.begin_run()

        class FakeStateChange:
            type = "state_change"
            iteration = 0
            data = {"action": "intent_shifted"}
            def to_dict(self):
                return {"type": self.type, "data": self.data}

        collector.record_agent_event(FakeStateChange())
        collector.record_agent_event(FakeStateChange())

        run = collector.end_run()
        assert run.raw_data["intent_shifts"] == 2
