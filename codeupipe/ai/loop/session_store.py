"""SessionStore — SQLite-backed session persistence.

Serializes AgentState + revised turn history to SQLite for
session resume after process restart.  Revision creates the
natural checkpoint — we persist the compressed version.

Usage:
    store = SessionStore(":memory:")  # or a file path
    store.save(session_id, state, context_snapshot)
    restored = store.load(session_id)
"""

from __future__ import annotations

import json
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

from codeupipe.ai.loop.state import AgentState, TurnRecord, TurnType

logger = logging.getLogger("codeupipe.ai.session")


def _serialize_state(state: AgentState) -> str:
    """Convert AgentState to JSON string."""
    turns = []
    for t in state.turn_history:
        turns.append({
            "iteration": t.iteration,
            "turn_type": t.turn_type.value,
            "input_prompt": t.input_prompt,
            "response_content": t.response_content,
            "tool_calls_count": t.tool_calls_count,
            "timestamp": t.timestamp.isoformat(),
        })

    return json.dumps({
        "loop_iteration": state.loop_iteration,
        "done": state.done,
        "max_iterations": state.max_iterations,
        "turn_history": turns,
        "active_capabilities": list(state.active_capabilities),
    })


def _deserialize_state(data: str) -> AgentState:
    """Restore AgentState from JSON string."""
    raw = json.loads(data)
    turns = []
    for t in raw.get("turn_history", []):
        turns.append(TurnRecord(
            iteration=t["iteration"],
            turn_type=TurnType(t["turn_type"]),
            input_prompt=t["input_prompt"],
            response_content=t.get("response_content"),
            tool_calls_count=t.get("tool_calls_count", 0),
            timestamp=datetime.fromisoformat(t["timestamp"]),
        ))

    return AgentState(
        loop_iteration=raw["loop_iteration"],
        done=raw["done"],
        max_iterations=raw["max_iterations"],
        turn_history=tuple(turns),
        active_capabilities=tuple(raw.get("active_capabilities", [])),
    )


class SessionCheckpoint:
    """A restored checkpoint with state and metadata."""

    def __init__(
        self,
        session_id: str,
        state: AgentState,
        context_snapshot: dict | None,
        created_at: datetime,
    ) -> None:
        self.session_id = session_id
        self.state = state
        self.context_snapshot = context_snapshot or {}
        self.created_at = created_at


class SessionStore:
    """SQLite-backed session checkpoint persistence."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS session_checkpoints (
                session_id TEXT NOT NULL,
                agent_state TEXT NOT NULL,
                context_snapshot TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (session_id, created_at)
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_latest
            ON session_checkpoints(session_id, created_at DESC)
        """)
        self._conn.commit()

    def save(
        self,
        session_id: str,
        state: AgentState,
        context_snapshot: dict | None = None,
    ) -> None:
        """Persist a checkpoint for the given session."""
        state_json = _serialize_state(state)
        ctx_json = json.dumps(context_snapshot or {}, default=str)
        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """
            INSERT INTO session_checkpoints
                (session_id, agent_state, context_snapshot, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, state_json, ctx_json, now),
        )
        self._conn.commit()
        logger.info("Saved checkpoint for session %s", session_id)

    def load(self, session_id: str) -> SessionCheckpoint | None:
        """Load the most recent checkpoint for a session."""
        row = self._conn.execute(
            """
            SELECT agent_state, context_snapshot, created_at
            FROM session_checkpoints
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()

        if not row:
            return None

        state = _deserialize_state(row["agent_state"])
        ctx_snap = json.loads(row["context_snapshot"]) if row["context_snapshot"] else {}
        created = datetime.fromisoformat(row["created_at"])

        return SessionCheckpoint(
            session_id=session_id,
            state=state,
            context_snapshot=ctx_snap,
            created_at=created,
        )

    def list_sessions(self) -> list[str]:
        """List all distinct session IDs with checkpoints."""
        rows = self._conn.execute(
            "SELECT DISTINCT session_id FROM session_checkpoints"
        ).fetchall()
        return [r["session_id"] for r in rows]

    def delete(self, session_id: str) -> int:
        """Delete all checkpoints for a session. Returns count deleted."""
        cursor = self._conn.execute(
            "DELETE FROM session_checkpoints WHERE session_id = ?",
            (session_id,),
        )
        self._conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
