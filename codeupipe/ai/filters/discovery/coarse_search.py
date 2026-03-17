"""CoarseSearchLink — Fast 256-dim vector search.

Uses the first 256 dimensions of the query embedding (MRL)
to quickly narrow down candidates from the full registry.

Input:  payload["query_embedding"] (np.ndarray), payload["registry"] (CapabilityRegistry)
Output: payload["coarse_results"] (list of (CapabilityDefinition, float))
"""

from codeupipe import Payload

from codeupipe.ai.config import get_settings
from codeupipe.ai.discovery.registry import CapabilityRegistry


class CoarseSearchLink:
    """Fast coarse vector search using truncated MRL dimensions."""

    async def call(self, payload: Payload) -> Payload:
        query_embedding = payload.get("query_embedding")
        if query_embedding is None:
            raise ValueError("query_embedding (np.ndarray) is required on context")

        registry = payload.get("capability_registry")
        if not isinstance(registry, CapabilityRegistry):
            raise ValueError(
                "capability_registry (CapabilityRegistry) is required on context"
            )

        settings = get_settings()
        capability_type = payload.get("capability_type")

        coarse_results = registry.vector_search(
            query_embedding=query_embedding,
            top_k=settings.coarse_search_top_k,
            use_coarse=True,
            coarse_dims=settings.coarse_search_dims,
            capability_type=capability_type,
        )

        # Hydrate IDs into full CapabilityDefinition objects
        hydrated = []
        for cap_id, score in coarse_results:
            cap = registry.get(cap_id)
            if cap is not None:
                hydrated.append((cap, score))

        return payload.insert("coarse_results", hydrated)
