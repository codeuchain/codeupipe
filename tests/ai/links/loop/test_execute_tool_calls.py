"""RED PHASE — Tests for ExecuteToolCallsLink.

ExecuteToolCallsLink detects tool_calls in last_response_event and
executes each via a ToolExecutor on context. When no tool_calls are
present (SDK-managed providers), it passes through unchanged.

Position in turn chain: after language_model, before process_response.
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.execute_tool_calls import ExecuteToolCallsLink
from codeupipe.ai.providers.base import ToolCall, ToolExecutor


# ── Helpers ─────────────────────────────────────────────────────────


class FakeExecutor:
    """Simple ToolExecutor that records calls and returns canned results."""

    def __init__(self, responses: dict[str, dict] | None = None):
        self.calls: list[tuple[str, str]] = []
        self._responses = responses or {}

    async def execute(self, name: str, arguments: str) -> dict:
        self.calls.append((name, arguments))
        if name in self._responses:
            return self._responses[name]
        return {"output": f"result_of_{name}"}


class FailingExecutor:
    """ToolExecutor that raises for specific tools."""

    def __init__(self, fail_on: set[str] | None = None):
        self._fail_on = fail_on or set()

    async def execute(self, name: str, arguments: str) -> dict:
        if name in self._fail_on:
            raise RuntimeError(f"Tool {name} exploded")
        return {"output": f"ok_{name}"}


# ── Tests ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestExecuteToolCallsLinkPassthrough:
    """Cases where the link should pass through without executing anything."""

    @pytest.mark.asyncio
    async def test_pass_through_no_event(self):
        """No last_response_event → pass through unchanged."""
        link = ExecuteToolCallsLink()
        ctx = Payload({"some_key": "value"})

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None
        assert result.get("follow_up_source") is None
        assert result.get("some_key") == "value"

    @pytest.mark.asyncio
    async def test_pass_through_non_dict_event(self):
        """last_response_event is not a dict → pass through."""
        link = ExecuteToolCallsLink()
        ctx = Payload({"last_response_event": "just a string"})

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None

    @pytest.mark.asyncio
    async def test_pass_through_no_tool_calls(self):
        """Event has no tool_calls → SDK handled it, pass through."""
        link = ExecuteToolCallsLink()
        ctx = Payload({
            "last_response_event": {
                "content": "Here's your answer",
                "tool_results": [{"output": "sdk did this"}],
            },
        })

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None
        assert result.get("follow_up_source") is None

    @pytest.mark.asyncio
    async def test_pass_through_empty_tool_calls(self):
        """Empty tool_calls list → pass through."""
        link = ExecuteToolCallsLink()
        ctx = Payload({
            "last_response_event": {
                "content": "Done",
                "tool_calls": [],
            },
        })

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None

    @pytest.mark.asyncio
    async def test_pass_through_no_executor(self):
        """tool_calls present but no tool_executor → pass through (logged)."""
        link = ExecuteToolCallsLink()
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"id": "tc_1", "name": "search", "arguments": "{}"},
                ],
            },
        })

        result = await link.call(ctx)

        # Should not set follow_up or modify event
        assert result.get("follow_up_prompt") is None
        assert result.get("follow_up_source") is None


@pytest.mark.unit
class TestExecuteToolCallsLinkExecution:
    """Cases where tool calls are actually executed."""

    @pytest.mark.asyncio
    async def test_executes_single_tool_call(self):
        """Single tool call → executed via executor, results merged."""
        link = ExecuteToolCallsLink()
        executor = FakeExecutor({"search": {"output": "found 3 items"}})
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"id": "tc_1", "name": "search", "arguments": '{"q": "test"}'},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        # Executor was called
        assert len(executor.calls) == 1
        assert executor.calls[0] == ("search", '{"q": "test"}')

        # Tool results merged into event
        event = result.get("last_response_event")
        assert len(event["tool_results"]) == 1
        assert event["tool_results"][0]["name"] == "search"
        assert event["tool_results"][0]["output"] == "found 3 items"
        assert event["tool_results"][0]["tool_call_id"] == "tc_1"

        # Follow-up set
        prompt = result.get("follow_up_prompt")
        assert prompt is not None
        assert "Tool results:" in prompt
        assert "found 3 items" in prompt
        assert result.get("follow_up_source") == "tool_execution"

    @pytest.mark.asyncio
    async def test_executes_multiple_tool_calls(self):
        """Multiple tool calls → all executed in order."""
        link = ExecuteToolCallsLink()
        executor = FakeExecutor({
            "search": {"output": "3 results"},
            "calculate": {"output": "42"},
        })
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"id": "tc_1", "name": "search", "arguments": "{}"},
                    {"id": "tc_2", "name": "calculate", "arguments": '{"x": 6, "y": 7}'},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        assert len(executor.calls) == 2
        assert executor.calls[0][0] == "search"
        assert executor.calls[1][0] == "calculate"

        event = result.get("last_response_event")
        assert len(event["tool_results"]) == 2
        assert event["tool_results"][0]["name"] == "search"
        assert event["tool_results"][1]["name"] == "calculate"

    @pytest.mark.asyncio
    async def test_merges_with_existing_tool_results(self):
        """Existing tool_results are preserved, new ones appended."""
        link = ExecuteToolCallsLink()
        executor = FakeExecutor({"echo": {"output": "hello"}})
        ctx = Payload({
            "last_response_event": {
                "tool_results": [
                    {"name": "prior_tool", "output": "old result"},
                ],
                "tool_calls": [
                    {"id": "tc_1", "name": "echo", "arguments": "{}"},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        event = result.get("last_response_event")
        assert len(event["tool_results"]) == 2
        assert event["tool_results"][0]["name"] == "prior_tool"
        assert event["tool_results"][1]["name"] == "echo"

    @pytest.mark.asyncio
    async def test_follow_up_prompt_contains_all_results(self):
        """Follow-up prompt summary includes output from each tool."""
        link = ExecuteToolCallsLink()
        executor = FakeExecutor({
            "read_file": {"output": "contents of main.py"},
            "list_dir": {"output": "src/ tests/ README.md"},
        })
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"id": "tc_1", "name": "read_file", "arguments": "{}"},
                    {"id": "tc_2", "name": "list_dir", "arguments": "{}"},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        assert "read_file" in prompt
        assert "contents of main.py" in prompt
        assert "list_dir" in prompt
        assert "src/ tests/ README.md" in prompt

    @pytest.mark.asyncio
    async def test_preserves_other_event_keys(self):
        """Non-tool-related keys in the event dict are preserved."""
        link = ExecuteToolCallsLink()
        executor = FakeExecutor()
        ctx = Payload({
            "last_response_event": {
                "content": "I'll search for you",
                "model": "gpt-4",
                "tool_calls": [
                    {"id": "tc_1", "name": "search", "arguments": "{}"},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        event = result.get("last_response_event")
        assert event["content"] == "I'll search for you"
        assert event["model"] == "gpt-4"


@pytest.mark.unit
class TestExecuteToolCallsLinkErrors:
    """Error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_tool_error_captured_in_results(self):
        """Executor raises → error captured in tool_results, not propagated."""
        link = ExecuteToolCallsLink()
        executor = FailingExecutor(fail_on={"broken_tool"})
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"id": "tc_1", "name": "broken_tool", "arguments": "{}"},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        event = result.get("last_response_event")
        assert len(event["tool_results"]) == 1
        assert event["tool_results"][0]["name"] == "broken_tool"
        assert "exploded" in event["tool_results"][0]["error"]
        assert event["tool_results"][0]["output"] == ""

    @pytest.mark.asyncio
    async def test_error_included_in_follow_up_prompt(self):
        """Tool errors show in the follow-up prompt for the LLM."""
        link = ExecuteToolCallsLink()
        executor = FailingExecutor(fail_on={"bad_tool"})
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"id": "tc_1", "name": "bad_tool", "arguments": "{}"},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        assert "Error" in prompt
        assert "bad_tool" in prompt

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self):
        """Some tools succeed, some fail → both recorded correctly."""
        link = ExecuteToolCallsLink()
        executor = FailingExecutor(fail_on={"flaky_tool"})
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"id": "tc_1", "name": "good_tool", "arguments": "{}"},
                    {"id": "tc_2", "name": "flaky_tool", "arguments": "{}"},
                    {"id": "tc_3", "name": "another_good", "arguments": "{}"},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        event = result.get("last_response_event")
        assert len(event["tool_results"]) == 3

        # First: success
        assert event["tool_results"][0]["name"] == "good_tool"
        assert event["tool_results"][0]["error"] is None
        assert "ok_good_tool" in event["tool_results"][0]["output"]

        # Second: failure
        assert event["tool_results"][1]["name"] == "flaky_tool"
        assert "exploded" in event["tool_results"][1]["error"]

        # Third: success
        assert event["tool_results"][2]["name"] == "another_good"
        assert event["tool_results"][2]["error"] is None

    @pytest.mark.asyncio
    async def test_tool_call_with_missing_id(self):
        """Tool call dict missing 'id' → uses empty string."""
        link = ExecuteToolCallsLink()
        executor = FakeExecutor()
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"name": "no_id_tool", "arguments": "{}"},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        event = result.get("last_response_event")
        assert event["tool_results"][0]["tool_call_id"] == ""
        assert event["tool_results"][0]["name"] == "no_id_tool"

    @pytest.mark.asyncio
    async def test_tool_call_with_missing_arguments(self):
        """Tool call dict missing 'arguments' → defaults to '{}'."""
        link = ExecuteToolCallsLink()
        executor = FakeExecutor()
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"id": "tc_1", "name": "no_args"},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        # Executor received default empty args
        assert executor.calls[0] == ("no_args", "{}")


@pytest.mark.unit
class TestExecuteToolCallsLinkIntegration:
    """Integration-like tests verifying compatibility with adjacent links."""

    @pytest.mark.asyncio
    async def test_follow_up_source_enables_process_response_turn_type(self):
        """follow_up_source='tool_execution' is compatible with ProcessResponseLink."""
        link = ExecuteToolCallsLink()
        executor = FakeExecutor()
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"id": "tc_1", "name": "search", "arguments": "{}"},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        # ProcessResponseLink._infer_turn_type checks this value
        assert result.get("follow_up_source") == "tool_execution"

    @pytest.mark.asyncio
    async def test_tool_results_format_for_tool_continuation(self):
        """Tool results format is compatible with ToolContinuationLink scanning."""
        link = ExecuteToolCallsLink()
        executor = FakeExecutor({"finder": {"output": "found it", "__follow_up__": True}})
        ctx = Payload({
            "last_response_event": {
                "tool_calls": [
                    {"id": "tc_1", "name": "finder", "arguments": "{}"},
                ],
            },
            "tool_executor": executor,
        })

        result = await link.call(ctx)

        # ToolContinuationLink scans tool_results for __follow_up__
        event = result.get("last_response_event")
        results = event["tool_results"]
        assert len(results) == 1
        # The result dict should contain __follow_up__ from the executor
        assert results[0].get("__follow_up__") is True

    @pytest.mark.asyncio
    async def test_sdk_provider_passthrough_pattern(self):
        """Simulates SDK provider pattern: no tool_calls, results pre-populated."""
        link = ExecuteToolCallsLink()
        # SDK providers return empty tool_calls and pre-fill tool_results
        ctx = Payload({
            "last_response_event": {
                "content": "Based on the search results...",
                "tool_results": [
                    {"name": "search", "output": "sdk-executed result"},
                ],
                "tool_calls": [],
            },
            "tool_executor": FakeExecutor(),  # present but should not be called
        })

        result = await link.call(ctx)

        # Event should be completely unchanged
        event = result.get("last_response_event")
        assert len(event["tool_results"]) == 1
        assert event["tool_results"][0]["output"] == "sdk-executed result"
        assert result.get("follow_up_prompt") is None


@pytest.mark.unit
class TestToolCallDataclass:
    """Verify ToolCall dataclass structure."""

    def test_tool_call_creation(self):
        """ToolCall is frozen dataclass with id, name, arguments."""
        tc = ToolCall(id="call_123", name="search", arguments='{"q": "test"}')
        assert tc.id == "call_123"
        assert tc.name == "search"
        assert tc.arguments == '{"q": "test"}'

    def test_tool_call_immutable(self):
        """ToolCall is frozen — cannot reassign fields."""
        tc = ToolCall(id="1", name="echo", arguments="{}")
        with pytest.raises(AttributeError):
            tc.name = "other"  # type: ignore[misc]

    def test_tool_call_equality(self):
        """Two ToolCalls with same fields are equal."""
        tc1 = ToolCall(id="1", name="search", arguments="{}")
        tc2 = ToolCall(id="1", name="search", arguments="{}")
        assert tc1 == tc2
