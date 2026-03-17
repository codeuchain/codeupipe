"""LanguageModelLink — The single interface between agent and LLM.

This link is the cell membrane: everything before it is our world
(context, prompts, preparation). Everything after it is theirs
(the LLM provider). The membrane's job is simple: string in, string out.

The provider is swappable — inject at construction time or place on
context. The link position in the chain never changes; only the
provider implementation inside it does.

Input:  next_prompt (str | None), provider (LanguageModelProvider, on payload or injected)
Output: response (str | None), last_response_event (dict | None)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codeupipe import Payload

if TYPE_CHECKING:
    from codeupipe.ai.providers.base import LanguageModelProvider

logger = logging.getLogger("codeupipe.ai.filters.language_model")


class LanguageModelLink:
    """Send a prompt to a language model and store the response.

    The only link that talks to the LLM. Upstream links prepare the
    prompt. Downstream links process the response. This link is the
    clean seam — everything before it is provider-agnostic, everything
    after it is provider-agnostic.

    Args:
        provider: Optional provider injected at construction time.
            If not given, reads ``provider`` from context (placed by
            InitProviderLink).  Constructor injection is preferred for
            testing and standalone usage.
    """

    def __init__(self, provider: LanguageModelProvider | None = None) -> None:
        self._provider = provider

    async def call(self, payload: Payload) -> Payload:
        provider = self._provider or payload.get("provider")
        if not provider:
            raise ValueError(
                "provider is required — inject via constructor "
                "or place a LanguageModelProvider on context"
            )

        next_prompt = payload.get("next_prompt")
        if next_prompt is None:
            # No prompt prepared — skip sending.
            # CheckDoneLink will evaluate whether the loop should end.
            # Do NOT overwrite response — preserve the last iteration's value.
            return payload.insert("last_response_event", None)

        logger.debug("Sending prompt (%d chars) to provider", len(next_prompt))

        model_response = await provider.send(next_prompt)

        # Primary output: the string response
        payload = payload.insert("response", model_response.content)

        # Normalized event dict for downstream links
        # (BackchannelLink, ToolContinuationLink, ContextAttributionLink)
        payload = payload.insert("last_response_event", model_response.to_event_dict())

        logger.debug(
            "Provider responded (content=%s, tool_results=%d)",
            "yes" if model_response.content else "no",
            len(model_response.tool_results),
        )

        return payload
