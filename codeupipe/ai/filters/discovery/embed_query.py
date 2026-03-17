"""EmbedQueryLink — Embed intent text to a query vector.

Takes the agent's natural-language intent and produces a
1024-dimensional query embedding using Snowflake Arctic.

Input:  payload["intent"] (str)
Output: payload["query_embedding"] (np.ndarray, 1024-dim)
"""

from codeupipe import Payload

from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder


class EmbedQueryLink:
    """Embed a natural-language intent into a query vector."""

    async def call(self, payload: Payload) -> Payload:
        intent = payload.get("intent") or None
        if not intent:
            raise ValueError("intent (str) is required on context")

        embedder = SnowflakeArcticEmbedder()
        query_embedding = embedder.embed_query(intent)

        return payload.insert("query_embedding", query_embedding)
