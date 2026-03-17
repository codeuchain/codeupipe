"""CheckDoneLink — Single authority for marking the agent loop done.

Inspects agent_state and context for completion conditions:
  1. next_prompt is None (ReadInputLink had no input to prepare)
  2. Max iterations reached (safety cap)
  3. Already marked done (idempotent check)

This is the ONLY link that marks state.done, ensuring a single
decision point for loop termination (industry standard pattern).

Input:  next_prompt (str|None), agent_state (AgentState)
Output: agent_state (AgentState, possibly marked done)
"""

from codeupipe import Payload

from codeupipe.ai.loop.state import AgentState


class CheckDoneLink:
    """Evaluate whether the agent loop should continue."""

    async def call(self, payload: Payload) -> Payload:
        state: AgentState = payload.get("agent_state")
        if not isinstance(state, AgentState):
            raise ValueError("agent_state (AgentState) is required on context")

        # Already marked done
        if state.done:
            return payload

        # Safety cap: prevent infinite loops
        if state.loop_iteration >= state.max_iterations:
            state = state.mark_done()
            return payload.insert("agent_state", state)

        # Single authority: check if ReadInputLink prepared a prompt
        next_prompt = payload.get("next_prompt")
        if next_prompt is None:
            # No prompt prepared — mark done
            state = state.mark_done()
            return payload.insert("agent_state", state)

        return payload
