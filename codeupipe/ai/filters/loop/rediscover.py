"""RediscoverLink — Re-run discovery when intent shifts.

When UpdateIntentLink detects an intent change (intent_changed=True),
this Link re-runs the existing IntentDiscoveryChain against the
new intent.  If intent hasn't changed, passes through unchanged.

This reuses the *entire* existing discovery pipeline — EmbedQuery,
CoarseSearch, FineRank, ValidateAvailability, FetchDefinitions,
GroupResults — with zero duplication.

Input:  intent (str), intent_changed (bool), capability_registry (CapabilityRegistry)
Output: capabilities (list), grouped_capabilities (dict) — refreshed if intent changed
"""

import logging

from codeupipe import Payload

logger = logging.getLogger("codeupipe.ai.loop")


class RediscoverLink:
    """Re-run discovery pipeline when intent shifts."""

    async def call(self, payload: Payload) -> Payload:
        intent_changed = payload.get("intent_changed")
        if not intent_changed:
            return payload

        # Only re-discover if we have a registry
        from codeupipe.ai.discovery.registry import CapabilityRegistry

        registry = payload.get("capability_registry")
        if not isinstance(registry, CapabilityRegistry):
            return payload

        intent = payload.get("intent") or ""
        if not intent:
            return payload

        logger.info("Re-discovering capabilities for shifted intent: %s", intent[:80])

        # Import and build the discovery chain — same one used pre-loop
        from codeupipe.ai.pipelines.intent_discovery import (
            build_intent_discovery_chain,
        )

        discovery_chain = build_intent_discovery_chain()
        result = await discovery_chain.run(payload)

        # Transfer refreshed capabilities back
        capabilities = result.get("capabilities") or []
        grouped = result.get("grouped_capabilities") or {}

        payload = payload.insert("capabilities", capabilities)
        payload = payload.insert("grouped_capabilities", grouped)

        logger.info(
            "Rediscovery found %d capabilities for new intent",
            len(capabilities),
        )

        return payload
