"""ContextAttributionLink — Track token usage by source.

After each turn, estimates how much of the context budget is
consumed by each source: turns, tools, notifications, system
messages, capabilities, and discovery results.

This data feeds into the ContextBudget tracker (P5) and is
captured by AuditMiddleware for observability.

Input:  turn_history, capabilities, grouped_capabilities, etc.
Output: context_attribution (list[ContextAttribution])
"""

from __future__ import annotations

import logging

from codeupipe import Payload

from codeupipe.ai.hooks.audit_event import ContextAttribution

logger = logging.getLogger("codeupipe.ai.loop")

# Rough token estimation: ~4 chars per token (GPT-family heuristic)
CHARS_PER_TOKEN = 4


def _estimate_tokens(obj: object) -> int:
    """Rough token count from string length of an object."""
    text = str(obj) if obj else ""
    return max(1, len(text) // CHARS_PER_TOKEN)


class ContextAttributionLink:
    """Estimate and attribute token usage by source."""

    async def call(self, payload: Payload) -> Payload:
        attributions: list[ContextAttribution] = []
        total_tokens = 0

        # 1. Turn history
        turn_history = payload.get("turn_history") or []
        turns_tokens = _estimate_tokens(turn_history)
        attributions.append(ContextAttribution(
            source="turns",
            estimated_tokens=turns_tokens,
            item_count=len(turn_history),
        ))
        total_tokens += turns_tokens

        # 2. Capabilities context
        capabilities = payload.get("capabilities") or []
        caps_tokens = _estimate_tokens(capabilities)
        attributions.append(ContextAttribution(
            source="capabilities",
            estimated_tokens=caps_tokens,
            item_count=len(capabilities),
        ))
        total_tokens += caps_tokens

        # 3. Grouped capabilities
        grouped = payload.get("grouped_capabilities") or {}
        grouped_tokens = _estimate_tokens(grouped)
        attributions.append(ContextAttribution(
            source="grouped_capabilities",
            estimated_tokens=grouped_tokens,
            item_count=len(grouped),
        ))
        total_tokens += grouped_tokens

        # 4. System / prompt
        prompt = payload.get("prompt") or ""
        system_tokens = _estimate_tokens(prompt)
        attributions.append(ContextAttribution(
            source="system",
            estimated_tokens=system_tokens,
            item_count=1 if prompt else 0,
        ))
        total_tokens += system_tokens

        # 5. Notifications (injected context)
        injected = payload.get("injected_notifications") or []
        notif_tokens = _estimate_tokens(injected)
        attributions.append(ContextAttribution(
            source="notifications",
            estimated_tokens=notif_tokens,
            item_count=len(injected),
        ))
        total_tokens += notif_tokens

        # 6. Tool results (from last response)
        last_event = payload.get("last_response_event")
        tool_tokens = 0
        tool_count = 0
        if last_event and isinstance(last_event, dict):
            result = last_event.get("result") or {}
            tool_calls = result.get("tool_calls") or []
            tool_count = len(tool_calls)
            tool_tokens = _estimate_tokens(tool_calls)
        attributions.append(ContextAttribution(
            source="tools",
            estimated_tokens=tool_tokens,
            item_count=tool_count,
        ))
        total_tokens += tool_tokens

        # Calculate percentages
        if total_tokens > 0:
            final: list[ContextAttribution] = []
            for attr in attributions:
                pct = round((attr.estimated_tokens / total_tokens) * 100, 1)
                final.append(ContextAttribution(
                    source=attr.source,
                    estimated_tokens=attr.estimated_tokens,
                    percentage=pct,
                    item_count=attr.item_count,
                    metadata=attr.metadata,
                ))
            attributions = final

        payload = payload.insert("context_attribution", attributions)
        payload = payload.insert("total_estimated_tokens", total_tokens)

        logger.debug(
            "Context attribution: %d total tokens across %d sources",
            total_tokens,
            len(attributions),
        )

        return payload
