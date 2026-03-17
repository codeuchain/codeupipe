"""InsertCapabilityLink — Store capabilities + embeddings in registry.

Takes embedded capabilities and inserts them into the SQLite
CapabilityRegistry. Skips duplicates gracefully.

Input:  payload["embedded_capabilities"] (list of (CapabilityDefinition, np.ndarray)),
        payload["capability_registry"] (CapabilityRegistry)
Output: payload["registered_count"] (int)
"""

from codeupipe import Payload

from codeupipe.ai.discovery.registry import CapabilityRegistry


class InsertCapabilityLink:
    """Insert embedded capabilities into the SQLite registry."""

    async def call(self, payload: Payload) -> Payload:
        embedded = payload.get("embedded_capabilities")
        if embedded is None:
            raise ValueError("embedded_capabilities is required on context")

        registry = payload.get("capability_registry")
        if not isinstance(registry, CapabilityRegistry):
            raise ValueError(
                "capability_registry (CapabilityRegistry) is required on context"
            )

        count = 0
        for cap, embedding in embedded:
            # Skip if already registered
            existing = registry.get_by_name(cap.name)
            if existing is not None:
                continue

            registry.insert(cap, embedding)
            count += 1

        return payload.insert("registered_count", count)
