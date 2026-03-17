"""RED PHASE — Tests for ToolContinuationLink.

ToolContinuationLink inspects tool results from the SDK response
for __follow_up__ markers and sets follow_up_prompt on context
to trigger another outer-loop iteration.

Convention:
    Tool results embed __follow_up__ key with:
    {
        "reason": "Why follow-up is needed",
        "action": "continue|retry|verify|review",
        "source": "tool_name"
    }
    Or simply __follow_up__: True for a generic continuation signal.
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.loop.tool_continuation import (
    FOLLOW_UP_KEY,
    ToolContinuationLink,
)


@pytest.mark.unit
class TestToolContinuationLink:
    """Unit tests for ToolContinuationLink."""

    # ── Pass-through cases ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_pass_through_no_event(self):
        """No last_response_event → pass through unchanged."""
        link = ToolContinuationLink()
        ctx = Payload({"some_key": "value"})

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None
        assert result.get("follow_up_source") is None

    @pytest.mark.asyncio
    async def test_pass_through_no_follow_up_in_results(self):
        """Tool result without __follow_up__ → no continuation."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {"output": "clean data", "status": "ok"},
            },
        })

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None
        assert result.get("follow_up_source") is None

    @pytest.mark.asyncio
    async def test_pass_through_empty_tool_results(self):
        """Event with no tool results → no continuation."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {"no_results": True},
        })

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None

    # ── Follow-up extraction ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_extracts_follow_up_from_single_result(self):
        """Single tool result with __follow_up__ triggers continuation."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    "data": [1, 2, 3],
                    FOLLOW_UP_KEY: {
                        "reason": "Partial results. 3 more pages available.",
                        "action": "continue",
                        "source": "database",
                    },
                },
            },
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        assert prompt is not None
        assert "Partial results" in prompt
        assert "database" in prompt
        assert "action: continue" in prompt

    @pytest.mark.asyncio
    async def test_sets_follow_up_source(self):
        """Sets follow_up_source = 'tool_continuation' for TurnType inference."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    FOLLOW_UP_KEY: {
                        "reason": "Need to verify",
                        "action": "verify",
                        "source": "api_server",
                    },
                },
            },
        })

        result = await link.call(ctx)

        assert result.get("follow_up_source") == "tool_continuation"

    @pytest.mark.asyncio
    async def test_extracts_from_tool_results_list(self):
        """Handles tool_results list with multiple results."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "tool_results": [
                    {
                        "output": "clean",
                    },
                    {
                        "output": "needs more",
                        FOLLOW_UP_KEY: {
                            "reason": "Rate limit hit, retry after 5s.",
                            "action": "retry",
                            "source": "api_server",
                        },
                    },
                ],
            },
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        assert prompt is not None
        assert "Rate limit" in prompt
        assert "action: retry" in prompt

    @pytest.mark.asyncio
    async def test_collects_multiple_follow_ups(self):
        """Multiple tool results with __follow_up__ are all collected."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "tool_results": [
                    {
                        FOLLOW_UP_KEY: {
                            "reason": "Page 1 of 5",
                            "action": "continue",
                            "source": "db",
                        },
                    },
                    {
                        FOLLOW_UP_KEY: {
                            "reason": "Cache expired",
                            "action": "retry",
                            "source": "cache",
                        },
                    },
                ],
            },
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        assert "Page 1 of 5" in prompt
        assert "Cache expired" in prompt
        assert "db" in prompt
        assert "cache" in prompt

    @pytest.mark.asyncio
    async def test_boolean_true_follow_up(self):
        """__follow_up__: True generates generic continuation signal."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    FOLLOW_UP_KEY: True,
                },
            },
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        assert prompt is not None
        assert "Tool requested follow-up" in prompt

    @pytest.mark.asyncio
    async def test_boolean_false_no_follow_up(self):
        """__follow_up__: False does not trigger continuation."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    FOLLOW_UP_KEY: False,
                },
            },
        })

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None

    # ── Edge cases ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_skips_follow_up_without_reason(self):
        """__follow_up__ dict without 'reason' is skipped."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    FOLLOW_UP_KEY: {
                        "action": "continue",
                        # no reason
                    },
                },
            },
        })

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None

    @pytest.mark.asyncio
    async def test_skips_follow_up_with_empty_reason(self):
        """__follow_up__ with empty reason string is skipped."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    FOLLOW_UP_KEY: {
                        "reason": "",
                        "action": "continue",
                    },
                },
            },
        })

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None

    @pytest.mark.asyncio
    async def test_defaults_action_to_continue(self):
        """Missing action defaults to 'continue'."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    FOLLOW_UP_KEY: {
                        "reason": "More data available",
                        "source": "db",
                    },
                },
            },
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        assert "action: continue" in prompt

    @pytest.mark.asyncio
    async def test_defaults_source_to_unknown(self):
        """Missing source defaults to 'unknown_tool'."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    FOLLOW_UP_KEY: {
                        "reason": "Need follow-up",
                    },
                },
            },
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        assert "unknown_tool" in prompt

    @pytest.mark.asyncio
    async def test_handles_session_event_like_object(self):
        """Handles event with .data attribute (SessionEvent-like)."""
        link = ToolContinuationLink()

        class MockEvent:
            data = {
                "result": {
                    FOLLOW_UP_KEY: {
                        "reason": "Via data attr",
                        "source": "mock",
                    },
                },
            }

        ctx = Payload({
            "last_response_event": MockEvent(),
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        assert "Via data attr" in prompt

    @pytest.mark.asyncio
    async def test_ignores_non_dict_non_bool_follow_up(self):
        """Non-dict, non-bool __follow_up__ values are ignored."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    FOLLOW_UP_KEY: "just a string",
                },
            },
        })

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None

    @pytest.mark.asyncio
    async def test_ignores_numeric_follow_up(self):
        """Numeric __follow_up__ values are ignored."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    FOLLOW_UP_KEY: 42,
                },
            },
        })

        result = await link.call(ctx)

        assert result.get("follow_up_prompt") is None

    @pytest.mark.asyncio
    async def test_prompt_format_structure(self):
        """Follow-up prompt has expected structure."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "result": {
                    FOLLOW_UP_KEY: {
                        "reason": "Verify deployment",
                        "action": "verify",
                        "source": "deploy_server",
                    },
                },
            },
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        # Should contain header
        assert "Tool results require follow-up:" in prompt
        # Should contain formatted line
        assert "[deploy_server] Verify deployment (action: verify)" in prompt
        # Should contain footer
        assert "Please continue processing" in prompt

    @pytest.mark.asyncio
    async def test_mixed_results_only_follow_up_ones_collected(self):
        """Only tool results WITH __follow_up__ contribute; others ignored."""
        link = ToolContinuationLink()
        ctx = Payload({
            "last_response_event": {
                "tool_results": [
                    {"output": "no follow-up here"},
                    {"output": "also clean"},
                    {
                        "output": "needs more",
                        FOLLOW_UP_KEY: {
                            "reason": "Incomplete scan",
                            "source": "scanner",
                        },
                    },
                ],
            },
        })

        result = await link.call(ctx)

        prompt = result.get("follow_up_prompt")
        assert "Incomplete scan" in prompt
        # Only one follow-up signal
        assert prompt.count("[") == 1  # one source bracket


@pytest.mark.unit
class TestToolContinuationWithProcessResponse:
    """Integration: LanguageModelLink sets last_response_event; ProcessResponseLink records turns."""

    @pytest.mark.asyncio
    async def test_process_response_records_turn(self):
        """ProcessResponseLink records response (set by LanguageModelLink) in turn history."""
        from codeupipe.ai.filters.loop.process_response import ProcessResponseLink
        from codeupipe.ai.loop.state import AgentState

        link = ProcessResponseLink()

        state = AgentState(loop_iteration=1)
        ctx = Payload({
            "agent_state": state,
            "response": "Response text",
            "next_prompt": "hello",
            "last_response_event": {"content": "Response text", "tool_results": []},
        })

        result = await link.call(ctx)

        new_state = result.get("agent_state")
        assert len(new_state.turn_history) == 1
        assert new_state.turn_history[0].response_content == "Response text"

    @pytest.mark.asyncio
    async def test_tool_continuation_turn_type(self):
        """ProcessResponseLink infers TOOL_CONTINUATION when follow_up_source is set."""
        from codeupipe.ai.filters.loop.process_response import ProcessResponseLink
        from codeupipe.ai.loop.state import AgentState, TurnType

        link = ProcessResponseLink()

        state = AgentState(loop_iteration=2)  # Not first turn
        ctx = Payload({
            "agent_state": state,
            "response": "Following up on tool results",
            "next_prompt": "Tool results require follow-up...",
            "follow_up_source": "tool_continuation",
        })

        result = await link.call(ctx)

        turn = result.get("agent_state").turn_history[0]
        assert turn.turn_type == TurnType.TOOL_CONTINUATION
