"""FineRankLink — Full 1024-dim re-ranking.

Takes coarse search results and re-ranks them using the full
1024-dimensional embedding for precise similarity scoring.

Input:  payload["coarse_results"], payload["query_embedding"], payload["capability_registry"]
Output: payload["ranked_results"] (list of (CapabilityDefinition, float), top 5)
"""

from codeupipe import Payload

from codeupipe.ai.config import get_settings
from codeupipe.ai.discovery.registry import CapabilityRegistry


class FineRankLink:
    """Re-rank coarse results using full-dimensional embeddings."""

    async def call(self, payload: Payload) -> Payload:
        coarse_results = payload.get("coarse_results")
        if coarse_results is None:
            raise ValueError("coarse_results is required on context")

        query_embedding = payload.get("query_embedding")
        if query_embedding is None:
            raise ValueError("query_embedding (np.ndarray) is required on context")

        registry = payload.get("capability_registry")
        if not isinstance(registry, CapabilityRegistry):
            raise ValueError(
                "capability_registry (CapabilityRegistry) is required on context"
            )

        settings = get_settings()

        # Re-rank using full 1024-dim vectors
        ranked_results = registry.vector_search(
            query_embedding=query_embedding,
            top_k=settings.fine_search_top_k,
            use_coarse=False,
        )

        # Hydrate IDs into full CapabilityDefinition objects
        hydrated = []
        for cap_id, score in ranked_results:
            cap = registry.get(cap_id)
            if cap is not None:
                hydrated.append((cap, score))

        return payload.insert("ranked_results", hydrated)
