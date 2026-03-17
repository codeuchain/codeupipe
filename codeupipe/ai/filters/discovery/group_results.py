"""GroupResultsLink — Group discovery results by capability type.

Takes the flat list of discovered capabilities and organizes
them by type so the agent can see what's available in each
category at a glance.

Input:  payload["capabilities"] (list of CapabilityDefinition)
Output: payload["grouped_capabilities"] (dict mapping CapabilityType → list)
"""

from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType


class GroupResultsLink:
    """Group discovered capabilities by their type.

    Produces a dict keyed by CapabilityType with lists of
    matching capabilities. Empty categories are included
    so the agent always sees the full structure.
    """

    async def call(self, payload: Payload) -> Payload:
        capabilities: list[CapabilityDefinition] = payload.get("capabilities") or []

        # Initialize all types with empty lists
        grouped: dict[str, list[CapabilityDefinition]] = {
            cap_type.value: [] for cap_type in CapabilityType
        }

        for cap in capabilities:
            type_key = cap.capability_type.value
            if type_key in grouped:
                grouped[type_key].append(cap)

        return payload.insert("grouped_capabilities", grouped)
