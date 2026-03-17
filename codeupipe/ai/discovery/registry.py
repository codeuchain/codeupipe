"""SQLite-backed capability registry with vector search.

Stores CapabilityDefinitions with their embeddings and supports:
  - CRUD operations
  - FTS5 full-text search on name + description
  - Vector cosine similarity search (coarse + fine MRL passes)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType


class CapabilityRegistry:
    """SQLite registry for discoverable capabilities.

    Each capability is stored with its embedding BLOB so that
    intent-based vector search can find relevant capabilities
    without the caller knowing their names.

    Args:
        db_path: Path to the SQLite database file.
                 Parent directories are created automatically.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # ── Schema ────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        """Create tables and FTS index if they don't exist."""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS capabilities (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT    UNIQUE NOT NULL,
                description     TEXT    NOT NULL DEFAULT '',
                capability_type TEXT    NOT NULL DEFAULT 'tool',
                server_name     TEXT    NOT NULL DEFAULT '',
                command         TEXT    NOT NULL DEFAULT '',
                args_schema     TEXT    NOT NULL DEFAULT '{}',
                embedding       BLOB,
                metadata        TEXT    NOT NULL DEFAULT '{}',
                source_path     TEXT    NOT NULL DEFAULT '',
                content_hash    TEXT    NOT NULL DEFAULT '',
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_capabilities_source_path
                ON capabilities(source_path) WHERE source_path != '';

            CREATE VIRTUAL TABLE IF NOT EXISTS capabilities_fts
                USING fts5(name, description, content=capabilities, content_rowid=id);

            -- Triggers to keep FTS in sync
            CREATE TRIGGER IF NOT EXISTS capabilities_ai AFTER INSERT ON capabilities
            BEGIN
                INSERT INTO capabilities_fts(rowid, name, description)
                VALUES (new.id, new.name, new.description);
            END;

            CREATE TRIGGER IF NOT EXISTS capabilities_ad AFTER DELETE ON capabilities
            BEGIN
                INSERT INTO capabilities_fts(capabilities_fts, rowid, name, description)
                VALUES ('delete', old.id, old.name, old.description);
            END;

            CREATE TRIGGER IF NOT EXISTS capabilities_au AFTER UPDATE ON capabilities
            BEGIN
                INSERT INTO capabilities_fts(capabilities_fts, rowid, name, description)
                VALUES ('delete', old.id, old.name, old.description);
                INSERT INTO capabilities_fts(rowid, name, description)
                VALUES (new.id, new.name, new.description);
            END;
            """
        )
        self._conn.commit()

    # ── Insert ────────────────────────────────────────────────────────

    def insert(
        self,
        capability: CapabilityDefinition,
        embedding: np.ndarray | None = None,
    ) -> int:
        """Insert a capability (with optional embedding) and return its id.

        Args:
            capability: The capability to persist.
            embedding: Numpy float32 vector (will be stored as BLOB).

        Returns:
            The database id of the inserted row.
        """
        embedding_blob: bytes | None = None
        if embedding is not None:
            embedding_blob = embedding.astype(np.float32).tobytes()

        cursor = self._conn.execute(
            """
            INSERT INTO capabilities
                (name, description, capability_type, server_name,
                 command, args_schema, embedding, metadata,
                 source_path, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                capability.name,
                capability.description,
                capability.capability_type.value,
                capability.server_name,
                capability.command,
                capability.args_schema_json(),
                embedding_blob,
                capability.metadata_json(),
                capability.source_path,
                capability.content_hash,
            ),
        )
        self._conn.commit()
        capability.id = cursor.lastrowid
        return cursor.lastrowid

    # ── Read ──────────────────────────────────────────────────────────

    def get(self, capability_id: int) -> CapabilityDefinition | None:
        """Get a capability by its database id."""
        row = self._conn.execute(
            "SELECT * FROM capabilities WHERE id = ?", (capability_id,)
        ).fetchone()
        return self._row_to_capability(row) if row else None

    def get_by_name(self, name: str) -> CapabilityDefinition | None:
        """Get a capability by its unique name."""
        row = self._conn.execute(
            "SELECT * FROM capabilities WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_capability(row) if row else None

    def list_all(
        self, type_filter: CapabilityType | None = None
    ) -> list[CapabilityDefinition]:
        """List all capabilities, optionally filtered by type."""
        if type_filter:
            rows = self._conn.execute(
                "SELECT * FROM capabilities WHERE capability_type = ? ORDER BY name",
                (type_filter.value,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM capabilities ORDER BY name"
            ).fetchall()
        return [self._row_to_capability(r) for r in rows]

    # ── Delete ────────────────────────────────────────────────────────

    def delete(self, capability_id: int) -> bool:
        """Delete a capability by id. Returns True if a row was removed."""
        cursor = self._conn.execute(
            "DELETE FROM capabilities WHERE id = ?", (capability_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_by_name(self, name: str) -> bool:
        """Delete a capability by name. Returns True if a row was removed."""
        cursor = self._conn.execute(
            "DELETE FROM capabilities WHERE name = ?", (name,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_by_server(self, server_name: str) -> int:
        """Delete all capabilities belonging to a server. Returns count removed."""
        cursor = self._conn.execute(
            "DELETE FROM capabilities WHERE server_name = ?", (server_name,)
        )
        self._conn.commit()
        return cursor.rowcount

    # ── Vector search ─────────────────────────────────────────────────

    def vector_search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 50,
        use_coarse: bool = False,
        coarse_dims: int = 256,
        capability_type: CapabilityType | None = None,
    ) -> list[tuple[int, float]]:
        """Search capabilities by embedding similarity.

        Args:
            query_embedding: Query vector (float32).
            top_k: Maximum results to return.
            use_coarse: If True, compare only the first coarse_dims dimensions.
            coarse_dims: Number of leading dimensions for coarse search.
            capability_type: Optional filter by capability type.

        Returns:
            List of (capability_id, similarity_score) tuples, descending.
        """
        query = "SELECT id, embedding FROM capabilities WHERE embedding IS NOT NULL"
        params: list = []
        if capability_type:
            query += " AND capability_type = ?"
            params.append(capability_type.value)

        rows = self._conn.execute(query, params).fetchall()

        results: list[tuple[int, float]] = []
        for row in rows:
            stored = np.frombuffer(row["embedding"], dtype=np.float32)

            if use_coarse:
                q_slice = query_embedding[:coarse_dims]
                s_slice = stored[:coarse_dims]
            else:
                q_slice = query_embedding
                s_slice = stored

            norm_q = np.linalg.norm(q_slice)
            norm_s = np.linalg.norm(s_slice)
            if norm_q == 0 or norm_s == 0:
                continue

            similarity = float(np.dot(q_slice, s_slice) / (norm_q * norm_s))
            results.append((row["id"], similarity))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # ── Full-text search ──────────────────────────────────────────────

    def text_search(
        self,
        query: str,
        type_filter: CapabilityType | None = None,
    ) -> list[CapabilityDefinition]:
        """Search capabilities using FTS5 full-text index.

        This is the fallback when embeddings are not available.
        """
        sql = """
            SELECT c.* FROM capabilities c
            JOIN capabilities_fts f ON c.id = f.rowid
            WHERE capabilities_fts MATCH ?
        """
        params: list = [query]
        if type_filter:
            sql += " AND c.capability_type = ?"
            params.append(type_filter.value)

        sql += " ORDER BY rank"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_capability(r) for r in rows]

    # ── Helpers ───────────────────────────────────────────────────────

    def get_by_source_path(self, source_path: str) -> CapabilityDefinition | None:
        """Get a capability by its source path."""
        row = self._conn.execute(
            "SELECT * FROM capabilities WHERE source_path = ?", (source_path,)
        ).fetchone()
        return self._row_to_capability(row) if row else None

    def delete_by_source_path(self, source_path: str) -> bool:
        """Delete a capability by source path. Returns True if removed."""
        cursor = self._conn.execute(
            "DELETE FROM capabilities WHERE source_path = ?", (source_path,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_capability(self, row: sqlite3.Row) -> CapabilityDefinition:
        """Convert a database row to a CapabilityDefinition."""
        return CapabilityDefinition(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            capability_type=CapabilityType(row["capability_type"]),
            server_name=row["server_name"],
            command=row["command"],
            args_schema=CapabilityDefinition.args_schema_from_json(row["args_schema"]),
            embedding=row["embedding"],
            metadata=CapabilityDefinition.metadata_from_json(row["metadata"]),
            source_path=row["source_path"],
            content_hash=row["content_hash"],
        )

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> CapabilityRegistry:
        return self

    def __exit__(self, *args) -> None:
        self.close()
