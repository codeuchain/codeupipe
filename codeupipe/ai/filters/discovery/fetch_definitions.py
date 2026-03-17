"""FetchDefinitionsLink — Load full CapabilityDefinition objects.

Extracts the CapabilityDefinition objects from the validated
search results, stripping the similarity scores.

Input:  payload["available_results"] (list of (CapabilityDefinition, float))
Output: payload["capabilities"] (list of CapabilityDefinition)
"""

from codeupipe import Payload


class FetchDefinitionsLink:
    """Extract CapabilityDefinition objects from scored results."""

    async def call(self, payload: Payload) -> Payload:
        available_results = payload.get("available_results")
        if available_results is None:
            raise ValueError("available_results is required on context")

        capabilities = [cap for cap, _score in available_results]

        return payload.insert("capabilities", capabilities)
