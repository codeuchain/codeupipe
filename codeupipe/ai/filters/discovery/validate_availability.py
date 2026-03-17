"""ValidateAvailabilityLink — Verify discovered capabilities still exist.

Filters ranked results to only include capabilities whose server
is still registered and reachable.

Input:  payload["ranked_results"] (list of (CapabilityDefinition, float))
Output: payload["available_results"] (list of (CapabilityDefinition, float))
"""

from codeupipe import Payload

from codeupipe.ai.discovery.registry import CapabilityRegistry


class ValidateAvailabilityLink:
    """Filter results to only capabilities whose servers exist in registry."""

    async def call(self, payload: Payload) -> Payload:
        ranked_results = payload.get("ranked_results")
        if ranked_results is None:
            raise ValueError("ranked_results is required on context")

        registry = payload.get("capability_registry")
        if not isinstance(registry, CapabilityRegistry):
            raise ValueError(
                "capability_registry (CapabilityRegistry) is required on context"
            )

        available = []
        for capability, score in ranked_results:
            # Verify the capability still exists in the registry
            existing = registry.get_by_name(capability.name)
            if existing is not None:
                available.append((capability, score))

        return payload.insert("available_results", available)
