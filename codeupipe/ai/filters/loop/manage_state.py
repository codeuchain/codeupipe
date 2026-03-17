"""ManageStateLink — Apply state mutations from agent decisions.

After ProcessResponseLink extracts the agent's response, this link
inspects the response and context for state-change signals:
  - Capability adoption (agent wants to load a skill/instruction)
  - Capability drop (agent wants to release a capability)

These mutations are applied to AgentState immutably.

If no state_updates are on context, passes through unchanged.

Input:  agent_state (AgentState), state_updates (list[dict], optional)
Output: agent_state (AgentState, with mutations applied)
"""

import logging

from codeupipe import Payload

from codeupipe.ai.loop.state import AgentState

logger = logging.getLogger("codeupipe.ai.loop")


class ManageStateLink:
    """Apply state mutations from agent decisions."""

    async def call(self, payload: Payload) -> Payload:
        state: AgentState = payload.get("agent_state")
        if not isinstance(state, AgentState):
            raise ValueError("agent_state (AgentState) is required on context")

        updates = payload.get("state_updates") or []
        if not updates:
            return payload

        for update in updates:
            if not isinstance(update, dict):
                continue

            action = update.get("action")
            name = update.get("name", "")

            if action == "adopt" and name:
                logger.info("Adopting capability: %s", name)
                state = state.add_capability(name)
            elif action == "drop" and name:
                logger.info("Dropping capability: %s", name)
                state = state.remove_capability(name)
            else:
                logger.warning("Unknown state update: %s", update)

        # Clear consumed updates
        payload = payload.insert("state_updates", [])
        return payload.insert("agent_state", state)
