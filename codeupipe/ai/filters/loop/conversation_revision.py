"""ConversationRevisionLink — Compress older turns when budget threshold crossed.

When the ContextBudgetTracker signals that revision is needed,
this Link compresses older turns in the turn history, preserving
the most recent `min_turns_kept` verbatim and summarizing the rest
into a single "session progress" block.

Strategy (heuristic first — agent self-summary as upgrade path):
  1. Preserve the most recent N turns verbatim
  2. Summarize older turns: keep turn_type + iteration, strip
     full response_content and input_prompt to summaries
  3. Create a "revised" TurnRecord with the summary

Input:  agent_state (AgentState), context_budget_tracker (ContextBudgetTracker)
Output: agent_state (AgentState — with revised turn_history if threshold crossed)
"""

from __future__ import annotations

import logging

from codeupipe import Payload

from codeupipe.ai.loop.context_budget import ContextBudgetTracker
from codeupipe.ai.loop.state import AgentState, TurnRecord, TurnType

logger = logging.getLogger("codeupipe.ai.loop")

# Max chars to keep in a summarized turn's content
_SUMMARY_MAX_CHARS = 120


def _summarize_turn(turn: TurnRecord) -> TurnRecord:
    """Compress a turn by truncating content to a short summary."""
    prompt_summary = (turn.input_prompt or "")[:_SUMMARY_MAX_CHARS]
    if len(turn.input_prompt or "") > _SUMMARY_MAX_CHARS:
        prompt_summary += "..."

    response_summary = (turn.response_content or "")[:_SUMMARY_MAX_CHARS]
    if len(turn.response_content or "") > _SUMMARY_MAX_CHARS:
        response_summary += "..."

    return TurnRecord(
        iteration=turn.iteration,
        turn_type=turn.turn_type,
        input_prompt=prompt_summary,
        response_content=response_summary,
        tool_calls_count=turn.tool_calls_count,
        timestamp=turn.timestamp,
    )


class ConversationRevisionLink:
    """Compress older turns when token budget threshold is crossed.

    Reads from context:
      - agent_state: AgentState with turn_history
      - context_budget_tracker: ContextBudgetTracker
      - total_estimated_tokens: int (from ContextAttributionLink)

    Writes to context:
      - agent_state: with revised turn_history (if revision occurred)
      - revision_applied: bool
    """

    async def call(self, payload: Payload) -> Payload:
        tracker = payload.get("context_budget_tracker")
        if not isinstance(tracker, ContextBudgetTracker):
            return payload.insert("revision_applied", False)

        state = payload.get("agent_state")
        if not isinstance(state, AgentState):
            return payload.insert("revision_applied", False)

        total_tokens = payload.get("total_estimated_tokens") or 0

        # Update the budget tracker
        # Build usage_by_source from context_attribution
        attributions = payload.get("context_attribution") or []
        usage_by_source = {}
        for attr in attributions:
            if hasattr(attr, "source") and hasattr(attr, "estimated_tokens"):
                usage_by_source[attr.source] = attr.estimated_tokens

        snapshot = tracker.update(total_tokens, usage_by_source)

        if not snapshot.needs_revision:
            return payload.insert("revision_applied", False)

        # Revision needed — compress older turns
        history = list(state.turn_history)
        min_kept = tracker.budget.min_turns_kept

        if len(history) <= min_kept:
            # Not enough turns to revise
            return payload.insert("revision_applied", False)

        # Split: older turns get summarized, recent kept verbatim
        keep_count = min(min_kept, len(history))
        older = history[: len(history) - keep_count]
        recent = history[len(history) - keep_count :]

        revised_older = [_summarize_turn(t) for t in older]

        logger.info(
            "Conversation revision: compressed %d older turns, kept %d recent",
            len(older),
            len(recent),
        )

        # Rebuild state with revised history
        revised_history = tuple(revised_older + recent)
        new_state = AgentState(
            loop_iteration=state.loop_iteration,
            done=state.done,
            max_iterations=state.max_iterations,
            turn_history=revised_history,
            active_capabilities=state.active_capabilities,
        )

        payload = payload.insert("agent_state", new_state)
        payload = payload.insert("revision_applied", True)

        return payload
