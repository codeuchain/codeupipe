"""IntentDiscoveryChain — Discover capabilities by natural-language intent.

Composes the discovery Links into a pipeline:
  EmbedQuery → CoarseSearch → FineRank → ValidateAvailability → FetchDefinitions

This is the core "intent → capabilities" flow. The agent declares
what it wants to do, and this chain returns matching capabilities.

Context requirements:
    - intent: str (natural language, e.g. "calculate the sum")
    - capability_registry: CapabilityRegistry

Context outputs:
    - capabilities: list[CapabilityDefinition]
    - query_embedding: np.ndarray
    - coarse_results: list[(CapabilityDefinition, float)]
    - ranked_results: list[(CapabilityDefinition, float)]
    - available_results: list[(CapabilityDefinition, float)]
"""

from codeupipe import Pipeline

from codeupipe.ai.filters.discovery.coarse_search import CoarseSearchLink
from codeupipe.ai.filters.discovery.embed_query import EmbedQueryLink
from codeupipe.ai.filters.discovery.fetch_definitions import FetchDefinitionsLink
from codeupipe.ai.filters.discovery.fine_rank import FineRankLink
from codeupipe.ai.filters.discovery.group_results import GroupResultsLink
from codeupipe.ai.filters.discovery.validate_availability import (
    ValidateAvailabilityLink,
)


def build_intent_discovery_chain() -> Pipeline:
    """Build the intent-based capability discovery chain.

    Flow:
        embed_query → coarse_search → fine_rank → validate → fetch → group

    The agent's intent flows in, matching capabilities flow out
    grouped by type (tool, skill, instruction, plan, prompt, resource).
    """
    chain = Pipeline()

    chain.add_filter(EmbedQueryLink(), "embed_query")
    chain.add_filter(CoarseSearchLink(), "coarse_search")
    chain.add_filter(FineRankLink(), "fine_rank")
    chain.add_filter(ValidateAvailabilityLink(), "validate_availability")
    chain.add_filter(FetchDefinitionsLink(), "fetch_definitions")
    chain.add_filter(GroupResultsLink(), "group_results")

    # Sequential pipeline — each step flows to the next

    return chain
