"""DiscoverByIntentLink — Bridge between session chain and discovery.

Takes the user's prompt as intent and runs it through the
IntentDiscoveryChain to find matching capabilities. If no
capability_registry is on context, passes through unchanged.

Input:  payload["prompt"] (str), payload["capability_registry"] (optional)
Output: payload["capabilities"] (list of CapabilityDefinition) if registry present
"""

from codeupipe import Payload


class DiscoverByIntentLink:
    """Discover capabilities by intent, or pass through if no registry."""

    async def call(self, payload: Payload) -> Payload:
        from codeupipe.ai.discovery.registry import CapabilityRegistry

        registry = payload.get("capability_registry")
        if not isinstance(registry, CapabilityRegistry):
            # No discovery registry — pass through unchanged
            return payload

        prompt = payload.get("prompt") or ""
        if not prompt:
            return payload

        # Import here to avoid circular deps and allow optional install
        try:
            from codeupipe.ai.pipelines.intent_discovery import (
                build_intent_discovery_chain,
            )
        except ImportError:
            # ai-discovery extras (torch/transformers) not installed — skip
            return payload

        # Run the discovery sub-chain
        try:
            discovery_chain = build_intent_discovery_chain()
            discovery_ctx = payload.insert("intent", prompt)
            result = await discovery_chain.run(discovery_ctx)
        except ImportError:
            # torch/transformers not installed — skip discovery gracefully
            return payload

        # Transfer discovered capabilities back
        capabilities = result.get("capabilities") or []
        grouped = result.get("grouped_capabilities") or {}
        payload = payload.insert("capabilities", capabilities)
        return payload.insert("grouped_capabilities", grouped)
