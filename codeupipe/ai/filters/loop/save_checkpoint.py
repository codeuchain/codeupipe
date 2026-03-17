"""SaveCheckpointLink — Persist session state after revision.

After ConversationRevisionLink compresses history, this Link
saves the compressed state to the SessionStore.  Natural
checkpoint: revision → save → resume picks up compressed version.

Input:  agent_state (AgentState), session_store (SessionStore),
        session_id (str), revision_applied (bool)
Output: checkpoint_saved (bool)
"""

from __future__ import annotations

import logging

from codeupipe import Payload

from codeupipe.ai.loop.session_store import SessionStore
from codeupipe.ai.loop.state import AgentState

logger = logging.getLogger("codeupipe.ai.session")


class SaveCheckpointLink:
    """Save session checkpoint after conversation revision."""

    async def call(self, payload: Payload) -> Payload:
        # Only save after a revision was applied
        revision_applied = payload.get("revision_applied")
        if not revision_applied:
            return payload.insert("checkpoint_saved", False)

        store = payload.get("session_store")
        if not isinstance(store, SessionStore):
            return payload.insert("checkpoint_saved", False)

        state = payload.get("agent_state")
        if not isinstance(state, AgentState):
            return payload.insert("checkpoint_saved", False)

        session_id = payload.get("session_id") or ""
        if not session_id:
            return payload.insert("checkpoint_saved", False)

        # Build a context snapshot — lightweight metadata
        snapshot = {
            "intent": payload.get("intent") or "",
            "loop_iteration": state.loop_iteration,
            "active_capabilities": list(state.active_capabilities),
            "total_estimated_tokens": payload.get("total_estimated_tokens") or 0,
        }

        try:
            store.save(session_id, state, snapshot)
            logger.info("Checkpoint saved for session %s", session_id)
            return payload.insert("checkpoint_saved", True)
        except Exception as exc:
            logger.warning("Failed to save checkpoint: %s", exc)
            return payload.insert("checkpoint_saved", False)
