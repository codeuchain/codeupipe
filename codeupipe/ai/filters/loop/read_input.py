"""ReadInputLink — Prepare the next prompt for the agent.

On the first iteration, uses the initial user prompt from context.
On subsequent iterations, formats follow-up context from previous
turn results and any pending notifications.

If no input is available (no follow-up, no notifications), sets
next_prompt to None to signal CheckDoneLink that the loop should end.

If persistent directives exist on context (from steer), they are
prepended to every prompt — Zone 1 (foundational) positioning.

Input:  prompt (str), agent_state (AgentState), directives (list[str], optional)
Output: next_prompt (str|None), agent_state (AgentState, incremented)
"""

from codeupipe import Payload

from codeupipe.ai.loop.state import AgentState


class ReadInputLink:
    """Prepare the next prompt for the agent turn."""

    async def call(self, payload: Payload) -> Payload:
        state: AgentState = payload.get("agent_state")
        if not isinstance(state, AgentState):
            raise ValueError("agent_state (AgentState) is required on context")

        if state.is_first_turn:
            # First iteration — use the initial user prompt
            prompt = payload.get("prompt")
            if not prompt:
                raise ValueError("prompt is required on context for first turn")
            next_prompt = prompt
        else:
            # Subsequent iteration — the previous response is already
            # in the session's conversation history.  Check if there's
            # an explicit follow-up or pending notifications.
            follow_up = payload.get("follow_up_prompt")
            notifications = payload.get("pending_notifications") or []

            if follow_up:
                next_prompt = follow_up
                # Clear the follow-up after consumption
                payload = payload.insert("follow_up_prompt", None)
                # Clear follow_up_source after next turn processes it
                # (ProcessResponseLink reads it for TurnType inference)
            elif notifications:
                # Format pending notifications as a system-style prompt
                formatted = self._format_notifications(notifications)
                next_prompt = formatted
                payload = payload.insert("pending_notifications", [])
            else:
                # No explicit follow-up and no notifications.
                # Set next_prompt to None to signal CheckDoneLink.
                next_prompt = None

        # Prepend persistent directives (steer) if any exist
        if next_prompt is not None:
            next_prompt = self._apply_directives(payload, next_prompt)

        payload = payload.insert("next_prompt", next_prompt)
        return payload.insert("agent_state", state.increment())

    @staticmethod
    def _apply_directives(payload: Payload, prompt: str) -> str:
        """Prepend persistent directives to the prompt.

        Directives are placed at the beginning (Zone 1 — foundational)
        so they frame the agent's response. The actual task remains
        at the end (Zone 3 — focal) for maximum attention weight.
        """
        directives = payload.get("directives") or []
        if not directives:
            return prompt

        header = "[Active Directives]\n"
        header += "\n".join(f"- {d}" for d in directives)
        header += "\n\n"
        return header + prompt

    @staticmethod
    def _format_notifications(notifications: list) -> str:
        """Format pending notifications into an agent-readable prompt."""
        lines = ["The following notifications arrived while you were working:\n"]
        for notif in notifications:
            if isinstance(notif, dict):
                source = notif.get("source", "system")
                message = notif.get("message", str(notif))
                lines.append(f"  [{source}] {message}")
            else:
                lines.append(f"  {notif}")
        lines.append("\nPlease acknowledge and handle these as appropriate.")
        return "\n".join(lines)
