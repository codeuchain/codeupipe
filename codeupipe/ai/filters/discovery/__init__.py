"""Discovery Links — intent-based capability search pipeline.

Links:
    EmbedQueryLink        — Embed intent text to a query vector
    CoarseSearchLink      — Fast 256-dim vector search (top 50)
    FineRankLink          — Full 1024-dim re-ranking (top 5)
    ValidateAvailabilityLink — Verify capabilities still exist
    FetchDefinitionsLink  — Load full CapabilityDefinition objects
    GroupResultsLink      — Group results by capability type
"""
