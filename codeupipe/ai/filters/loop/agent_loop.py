"""AgentLoopLink — Wraps a sub-chain and runs it in a loop.

This Link implements the core loop pattern: given a Chain of
turn-level Links (read → language_model → process → check_done),
it runs that chain repeatedly until agent_state.done is True.

The loop itself is a Link, so it composes naturally into
AgentSessionChain.

Input:  prompt (str), provider (LanguageModelProvider), agent_state (AgentState — auto-created if missing)
Output: response (str), agent_state (AgentState — final state with full turn history)
"""

import logging

from codeupipe import Payload, Pipeline

from codeupipe.ai.filters.loop.backchannel import BackchannelLink
from codeupipe.ai.filters.loop.check_done import CheckDoneLink
from codeupipe.ai.filters.loop.context_attribution import ContextAttributionLink
from codeupipe.ai.filters.loop.context_pruning import ContextPruningLink
from codeupipe.ai.filters.loop.conversation_revision import ConversationRevisionLink
from codeupipe.ai.filters.loop.execute_tool_calls import ExecuteToolCallsLink
from codeupipe.ai.filters.loop.inject_notifications import InjectNotificationsLink
from codeupipe.ai.filters.loop.manage_state import ManageStateLink
from codeupipe.ai.filters.loop.process_response import ProcessResponseLink
from codeupipe.ai.filters.loop.read_input import ReadInputLink
from codeupipe.ai.filters.loop.rediscover import RediscoverLink
from codeupipe.ai.filters.loop.save_checkpoint import SaveCheckpointLink
from codeupipe.ai.filters.loop.tool_continuation import ToolContinuationLink
from codeupipe.ai.filters.loop.update_intent import UpdateIntentLink
from codeupipe.ai.loop.state import AgentState

logger = logging.getLogger("codeupipe.ai.loop")


def build_turn_chain() -> Pipeline:
    """Build the single-turn sub-chain.

    Flow per iteration (15 filters):
        inject_notifications → read_input → language_model →
        execute_tool_calls → process_response → backchannel →
        tool_continuation → update_intent → rediscover →
        manage_state → context_attribution → conversation_revision →
        save_checkpoint → context_pruning → check_done

    InjectNotificationsLink drains the NotificationQueue (if present)
    before ReadInputLink decides what to send next.

    LanguageModelLink is the single interface to the LLM. It reads
    next_prompt from context, sends it to the configured provider,
    and stores the response string and normalized event dict.
    The provider is read from context (placed by InitProviderLink).

    ExecuteToolCallsLink detects pending tool_calls in the response
    and executes them via the ToolExecutor on context. SDK-based
    providers (e.g., CopilotProvider) handle tools internally, so
    tool_calls will be empty and this link passes through. For
    HTTP-based providers, this enables pipeline-managed tool execution.

    BackchannelLink extracts embedded notifications from tool results
    and pushes them to the queue for the *next* iteration.

    ToolContinuationLink inspects tool results for __follow_up__
    markers and sets follow_up_prompt to trigger another outer-loop
    iteration when tools signal more work is needed.

    UpdateIntentLink detects intent shifts from agent output.
    RediscoverLink re-runs the discovery pipeline when intent changes.

    ManageStateLink applies any state_updates (capability adopt/drop)
    after the agent responds.

    ContextAttributionLink tracks token usage by source for
    observability and budget management.

    ConversationRevisionLink compresses older turns when the token
    budget threshold is crossed.

    SaveCheckpointLink persists session state after revision for
    session resume capability.

    ContextPruningLink trims stale turn history and cleared response
    data to keep within the context budget.

    CheckDoneLink evaluates whether the loop should continue.
    """
    from codeupipe.ai.filters.language_model import LanguageModelLink

    chain = Pipeline()

    chain.add_filter(InjectNotificationsLink(), "inject_notifications")
    chain.add_filter(ReadInputLink(), "read_input")
    chain.add_filter(LanguageModelLink(), "language_model")
    chain.add_filter(ExecuteToolCallsLink(), "execute_tool_calls")
    chain.add_filter(ProcessResponseLink(), "process_response")
    chain.add_filter(BackchannelLink(), "backchannel")
    chain.add_filter(ToolContinuationLink(), "tool_continuation")
    chain.add_filter(UpdateIntentLink(), "update_intent")
    chain.add_filter(RediscoverLink(), "rediscover")
    chain.add_filter(ManageStateLink(), "manage_state")
    chain.add_filter(ContextAttributionLink(), "context_attribution")
    chain.add_filter(ConversationRevisionLink(), "conversation_revision")
    chain.add_filter(SaveCheckpointLink(), "save_checkpoint")
    chain.add_filter(ContextPruningLink(), "context_pruning")
    chain.add_filter(CheckDoneLink(), "check_done")


    return chain


class AgentLoopLink:
    """Run the turn chain in a loop until the agent is done.

    Creates AgentState if not present on context (backward compatible
    with single-prompt usage — one turn, auto-done).
    """

    def __init__(self, turn_chain: Pipeline | None = None) -> None:
        self._turn_chain = turn_chain or build_turn_chain()

    async def call(self, payload: Payload) -> Payload:
        # Bootstrap AgentState if not provided
        state = payload.get("agent_state")
        if not isinstance(state, AgentState):
            max_iter = payload.get("max_iterations") or 10
            state = AgentState(max_iterations=max_iter)
            payload = payload.insert("agent_state", state)

        # The loop: run the turn chain until done
        while True:
            logger.info("Loop iteration %d starting", payload.get("agent_state").loop_iteration)

            # Run one complete turn: read → send → process → check_done
            payload = await self._turn_chain.run(payload)

            # CheckDoneLink is the single authority for marking done
            state = payload.get("agent_state")
            if state.done:
                logger.info(
                    "Loop complete after %d iterations (done=%s, max=%s)",
                    state.loop_iteration,
                    state.done,
                    state.hit_max_iterations,
                )
                break

        return payload
