"""ResumeSessionLink — Restore session state from a checkpoint.

Runs early in the session chain (before the loop) to check if
a previous session can be resumed.  If a checkpoint exists,
restores AgentState with revised turn history and context
metadata.

Input:  session_id (str), session_store (SessionStore)
Output: agent_state (AgentState — restored if checkpoint found),
        resumed (bool)
"""

from __future__ import annotations

import logging

from codeupipe import Payload

from codeupipe.ai.loop.session_store import SessionStore

logger = logging.getLogger("codeupipe.ai.session")


class ResumeSessionLink:
    """Restore agent state from a saved checkpoint."""

    async def call(self, payload: Payload) -> Payload:
        store = payload.get("session_store")
        if not isinstance(store, SessionStore):
            return payload.insert("resumed", False)

        session_id = payload.get("session_id") or ""
        if not session_id:
            return payload.insert("resumed", False)

        checkpoint = store.load(session_id)
        if not checkpoint:
            logger.debug("No checkpoint found for session %s", session_id)
            return payload.insert("resumed", False)

        logger.info(
            "Resuming session %s from checkpoint (iteration %d, %d turns)",
            session_id,
            checkpoint.state.loop_iteration,
            len(checkpoint.state.turn_history),
        )

        # Restore state
        payload = payload.insert("agent_state", checkpoint.state)

        # Restore context snapshot metadata
        for key, value in checkpoint.context_snapshot.items():
            if key not in ("loop_iteration",):  # already in agent_state
                payload = payload.insert(key, value)

        payload = payload.insert("resumed", True)
        return payload
