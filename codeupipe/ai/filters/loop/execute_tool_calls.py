"""ExecuteToolCallsLink — Execute pending tool calls from the model.

When a provider returns tool_calls (pending invocations) instead of
handling them internally, this link:
  1. Detects tool_calls in last_response_event
  2. Executes each via the ToolExecutor on context
  3. Merges tool results into last_response_event.tool_results
  4. Sets follow_up_prompt so ReadInputLink feeds results back to the LLM

SDK-based providers (e.g., CopilotProvider with send_and_wait) handle
tool execution internally — tool_calls will be empty and this link
passes through. This enables both patterns:
  - SDK-managed tools (Copilot SDK, Anthropic SDK)
  - Pipeline-managed tools (direct HTTP, browser, custom providers)

Position in turn chain: after language_model, before process_response.

Input:  last_response_event (dict with tool_calls), tool_executor (ToolExecutor, optional)
Output: last_response_event (dict with tool_results), follow_up_prompt (str), follow_up_source (str)
"""

import json
import logging

from codeupipe import Payload

logger = logging.getLogger("codeupipe.ai.loop")


class ExecuteToolCallsLink:
    """Execute pending tool calls and feed results back to the LLM."""

    async def call(self, payload: Payload) -> Payload:
        event = payload.get("last_response_event")
        if event is None:
            return payload

        if not isinstance(event, dict):
            return payload

        tool_calls = event.get("tool_calls") or []
        if not tool_calls:
            return payload

        # Need a tool executor to run calls
        executor = payload.get("tool_executor")
        if executor is None:
            # No executor — can't execute tools, pass through.
            # SDK-based providers never reach here because they
            # return empty tool_calls.
            logger.debug(
                "tool_calls present but no tool_executor on context — skipping"
            )
            return payload

        # Execute each tool call
        results: list[dict] = []
        for tc in tool_calls:
            tc_id = tc.get("id", "")
            tc_name = tc.get("name", "")
            tc_args = tc.get("arguments", "{}")

            try:
                result = await executor.execute(tc_name, tc_args)
                results.append({
                    "tool_call_id": tc_id,
                    "name": tc_name,
                    "output": result.get("output", ""),
                    "error": result.get("error"),
                    **result,
                })
            except Exception as exc:
                logger.warning(
                    "Tool %s failed: %s", tc_name, exc, exc_info=True
                )
                results.append({
                    "tool_call_id": tc_id,
                    "name": tc_name,
                    "output": "",
                    "error": str(exc),
                })

        # Merge tool results into the event dict for downstream links
        # (BackchannelLink reads __notifications__, ToolContinuationLink
        # reads __follow_up__ from these results)
        existing_results = list(event.get("tool_results") or [])
        existing_results.extend(results)

        updated_event = {
            **event,
            "tool_results": existing_results,
        }
        payload = payload.insert("last_response_event", updated_event)

        # Build a summary for the follow-up prompt
        lines = []
        for r in results:
            name = r.get("name", "unknown")
            error = r.get("error")
            if error:
                lines.append(f"[{name}] Error: {error}")
            else:
                output = r.get("output", "")
                lines.append(f"[{name}] {output}")

        summary = "\n".join(lines)

        logger.info(
            "Executed %d tool call(s): %s",
            len(results),
            ", ".join(r.get("name", "?") for r in results),
        )

        payload = payload.insert(
            "follow_up_prompt",
            f"Tool results:\n{summary}\n\nPlease respond to the user based on these tool results.",
        )
        payload = payload.insert("follow_up_source", "tool_execution")

        return payload
