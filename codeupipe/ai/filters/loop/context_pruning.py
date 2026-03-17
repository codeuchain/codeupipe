"""ContextPruningLink — Remove stale context to stay within budget.

Runs after ManageStateLink, before CheckDoneLink.  On each
iteration, estimates how much context the agent is using and
prunes dropped capabilities and old turn history that exceed the
budget.

This is a heuristic link — the SDK manages the actual context
window, but we help by cleaning up data structures on our side
so stale information doesn't re-enter the prompt.

Input:  agent_state (AgentState), context_budget (int, optional)
Output: agent_state (AgentState, potentially trimmed history),
        pruned_keys (list[str]) — keys removed this iteration
"""

import logging

from codeupipe import Payload

from codeupipe.ai.loop.state import AgentState

logger = logging.getLogger("codeupipe.ai.loop")

# Rough token estimation: ~4 chars per token
CHARS_PER_TOKEN = 4

# Default context budget in tokens if none provided
DEFAULT_BUDGET = 128_000

# Keep at least this many recent turns regardless of budget
MIN_TURNS_KEPT = 3


class ContextPruningLink:
    """Prune stale context to keep within budget."""

    async def call(self, payload: Payload) -> Payload:
        state: AgentState = payload.get("agent_state")
        if not isinstance(state, AgentState):
            raise ValueError("agent_state (AgentState) is required on context")

        budget = payload.get("context_budget") or DEFAULT_BUDGET
        pruned_keys: list[str] = []

        # ── 1. Trim turn history ─────────────────────────────────────
        # Estimate tokens used by turn history
        history = state.turn_history
        if len(history) > MIN_TURNS_KEPT:
            total_chars = sum(
                len(t.input_prompt or "")
                + len(t.response_content or "")
                for t in history
            )
            estimated_tokens = total_chars // CHARS_PER_TOKEN

            # If history alone exceeds 50% of budget, trim oldest turns
            if estimated_tokens > budget // 2:
                keep_count = max(MIN_TURNS_KEPT, len(history) // 2)
                trimmed = history[-keep_count:]
                state = AgentState(
                    loop_iteration=state.loop_iteration,
                    done=state.done,
                    max_iterations=state.max_iterations,
                    turn_history=trimmed,
                    active_capabilities=state.active_capabilities,
                )
                removed_count = len(history) - keep_count
                logger.info(
                    "Pruned %d old turns from history (%d → %d)",
                    removed_count,
                    len(history),
                    keep_count,
                )
                pruned_keys.append(f"turn_history:{removed_count}_turns")

        # ── 2. Clear stale response data ─────────────────────────────
        # If last_response_event exists and we've already processed it,
        # remove the raw event to save memory (ProcessResponseLink
        # already extracted content into the turn record)
        if payload.get("last_response_event") is not None and len(history) > 0:
            payload = payload.insert("last_response_event", None)
            pruned_keys.append("last_response_event")

        # ── 3. Mark what we pruned ───────────────────────────────────
        existing_pruned = payload.get("pruned_keys") or []
        payload = payload.insert("pruned_keys", existing_pruned + pruned_keys)
        payload = payload.insert("agent_state", state)

        if pruned_keys:
            logger.debug("Context pruning this iteration: %s", pruned_keys)

        return payload
