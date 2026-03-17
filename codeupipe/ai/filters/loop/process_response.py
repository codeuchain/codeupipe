"""ProcessResponseLink — Record the turn in agent state.

LanguageModelLink places ``response`` (str) and ``last_response_event``
(dict) on context. This link's job is simpler now: read the response,
record it as a TurnRecord in AgentState, and move on.

If next_prompt was None (LanguageModelLink skipped), this link also
skips — CheckDoneLink will mark the loop complete.

Input:  response (str | None), agent_state (AgentState), next_prompt (str | None)
Output: agent_state (AgentState, with TurnRecord appended)
"""

from codeupipe import Payload

from codeupipe.ai.loop.state import AgentState, TurnRecord, TurnType


class ProcessResponseLink:
    """Record the turn in agent state from the model response."""

    async def call(self, payload: Payload) -> Payload:
        state: AgentState = payload.get("agent_state")
        if not isinstance(state, AgentState):
            raise ValueError("agent_state (AgentState) is required on context")

        next_prompt = payload.get("next_prompt")
        response = payload.get("response")

        # If LanguageModelLink skipped (next_prompt was None), skip processing
        if next_prompt is None:
            return payload

        # Determine turn type from what triggered this turn
        turn_type = self._infer_turn_type(payload)

        # Build the turn record
        turn = TurnRecord(
            iteration=state.loop_iteration - 1,  # already incremented by ReadInput
            turn_type=turn_type,
            input_prompt=next_prompt or "",
            response_content=response,
        )

        # Update state with the recorded turn
        state = state.record_turn(turn)

        return payload.insert("agent_state", state)

    @staticmethod
    def _infer_turn_type(payload: Payload) -> TurnType:
        """Infer what kind of input triggered this turn."""
        state: AgentState = payload.get("agent_state")
        if state.loop_iteration <= 1:
            return TurnType.USER_PROMPT

        # Check if this turn was triggered by tool continuation
        follow_up_source = payload.get("follow_up_source")
        if follow_up_source == "tool_continuation":
            return TurnType.TOOL_CONTINUATION

        if payload.get("follow_up_prompt"):
            return TurnType.FOLLOW_UP
        return TurnType.FOLLOW_UP
