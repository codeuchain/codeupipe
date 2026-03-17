"""UpdateIntentLink — Detect intent changes in agent output.

After the agent responds, this Link inspects the response and
state_updates for intent shift signals.  If the agent's response
or an explicit state_update indicates a new intent, it updates
the `intent` key on context so RediscoverLink can re-run discovery.

The agent can signal an intent shift two ways:
  1. Explicit state_update: {"action": "update_intent", "intent": "new intent"}
  2. Context key: follow_up_intent set by external logic

If no intent change is detected, passes through unchanged.

Input:  state_updates (list[dict], optional), intent (str, optional)
Output: intent (str, updated if changed), intent_changed (bool)
"""

import logging

from codeupipe import Payload

logger = logging.getLogger("codeupipe.ai.loop")


class UpdateIntentLink:
    """Detect and apply intent changes from agent output."""

    async def call(self, payload: Payload) -> Payload:
        current_intent = payload.get("intent") or payload.get("prompt") or ""
        new_intent: str | None = None

        # Check state_updates for explicit intent shift
        updates = payload.get("state_updates") or []
        remaining: list[dict] = []
        for update in updates:
            if not isinstance(update, dict):
                remaining.append(update)
                continue
            if update.get("action") == "update_intent":
                candidate = update.get("intent", "").strip()
                if candidate:
                    new_intent = candidate
                    logger.info(
                        "Intent shift detected: %s → %s",
                        current_intent[:60],
                        new_intent[:60],
                    )
                # Consumed — don't pass to ManageStateLink
            else:
                remaining.append(update)

        # Also check for follow_up_intent key (external injection)
        follow_up_intent = payload.get("follow_up_intent")
        if follow_up_intent and isinstance(follow_up_intent, str):
            new_intent = follow_up_intent.strip()
            payload = payload.insert("follow_up_intent", None)  # consumed

        if new_intent and new_intent != current_intent:
            payload = payload.insert("intent", new_intent)
            payload = payload.insert("intent_changed", True)
            payload = payload.insert("last_intent", current_intent)
        else:
            payload = payload.insert("intent_changed", False)

        # Write back remaining state_updates (consumed update_intent)
        if len(remaining) != len(updates):
            payload = payload.insert("state_updates", remaining)

        return payload
