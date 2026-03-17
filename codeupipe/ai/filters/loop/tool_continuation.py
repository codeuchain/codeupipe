"""ToolContinuationLink — Inspect tool results for follow-up signals.

The SDK's inner loop handles tool_use → execute → feed result back
until the model says end_turn. By the time send_and_wait() returns,
all tool calls are complete.

But a tool may embed explicit follow-up signals in its results that
the model doesn't know about or can't act on within a single turn.
This link inspects tool results for __follow_up__ markers and sets
follow_up_prompt on context to trigger another outer-loop iteration.

Convention:
    Tools embed a __follow_up__ key in their result dict:
    {
        "status": "ok",
        "data": {...},
        "__follow_up__": {
            "reason": "Partial results. 3 more pages available.",
            "action": "continue",   # continue | retry | verify | review
            "source": "database"    # optional: tool/server name
        }
    }

Multiple tool results can each carry __follow_up__. All are
collected, formatted, and set as the follow_up_prompt.

This link also sets follow_up_source = "tool_continuation" on
context so ProcessResponseLink can infer TurnType.TOOL_CONTINUATION
on the next iteration.

Input:  turn_event (SessionEvent | dict | None)
Output: follow_up_prompt (str | None), follow_up_source (str | None)
"""

import logging

from codeupipe import Payload

logger = logging.getLogger("codeupipe.ai.loop")

# Convention: tools embed this key in results to request follow-up
FOLLOW_UP_KEY = "__follow_up__"


class ToolContinuationLink:
    """Inspect tool results for follow-up signals and set continuation prompt."""

    async def call(self, payload: Payload) -> Payload:
        event = payload.get("last_response_event")
        if event is None:
            return payload

        # Extract tool results from the response event
        tool_results = self._extract_tool_results(event)

        # Collect follow-up signals from all tool results
        follow_ups = []
        for result in tool_results:
            follow_up = self._extract_follow_up(result)
            if follow_up:
                follow_ups.append(follow_up)

        if not follow_ups:
            return payload

        # Format all follow-up signals into a single prompt
        prompt = self._format_follow_up_prompt(follow_ups)
        logger.info(
            "Tool continuation triggered: %d follow-up signal(s)",
            len(follow_ups),
        )

        payload = payload.insert("follow_up_prompt", prompt)
        payload = payload.insert("follow_up_source", "tool_continuation")
        return payload

    def _extract_tool_results(self, event: object) -> list[dict]:
        """Pull tool result dicts from a response event.

        Handles both raw dicts and SessionEvent-like objects with
        .data attribute. Same extraction pattern as BackchannelLink
        for consistency.
        """
        results: list[dict] = []

        if isinstance(event, dict):
            if "result" in event and isinstance(event["result"], dict):
                results.append(event["result"])
            if "tool_results" in event:
                for r in event["tool_results"]:
                    if isinstance(r, dict):
                        results.append(r)
        elif hasattr(event, "data"):
            data = event.data
            if isinstance(data, dict):
                if "result" in data and isinstance(data["result"], dict):
                    results.append(data["result"])
                if "tool_results" in data:
                    for r in data["tool_results"]:
                        if isinstance(r, dict):
                            results.append(r)
            elif data is not None:
                # Dataclass or object with tool_results attribute
                if hasattr(data, "tool_results") and data.tool_results:
                    for r in data.tool_results:
                        if isinstance(r, dict):
                            results.append(r)

        return results

    def _extract_follow_up(self, result: dict) -> dict | None:
        """Extract a follow-up signal from a single tool result.

        Returns a normalized dict with reason, action, source or None.
        """
        raw = result.get(FOLLOW_UP_KEY)
        if not raw:
            return None

        if isinstance(raw, dict):
            reason = raw.get("reason", "")
            if not reason:
                return None
            return {
                "reason": reason,
                "action": raw.get("action", "continue"),
                "source": raw.get("source", "unknown_tool"),
            }

        # Boolean true — generic "continue" signal
        if raw is True:
            return {
                "reason": "Tool requested follow-up.",
                "action": "continue",
                "source": "unknown_tool",
            }

        return None

    @staticmethod
    def _format_follow_up_prompt(follow_ups: list[dict]) -> str:
        """Format collected follow-up signals into an agent-readable prompt."""
        lines = [
            "Tool results require follow-up:\n",
        ]
        for fu in follow_ups:
            source = fu.get("source", "unknown_tool")
            reason = fu.get("reason", "")
            action = fu.get("action", "continue")
            lines.append(f"  [{source}] {reason} (action: {action})")

        lines.append(
            "\nPlease continue processing based on these tool results."
        )
        return "\n".join(lines)
