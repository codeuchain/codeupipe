"""InitProviderLink — Initialize a language model provider.

Replaces the InitClientLink + CreateSessionLink pair.
Reads provider-specific kwargs from context (e.g. mcp_servers)
and calls provider.start(). Places the provider on context so
LanguageModelLink can find it.

Input:  mcp_servers (dict, optional — from RegisterServersLink)
Output: provider (LanguageModelProvider — started and ready)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codeupipe import Payload

if TYPE_CHECKING:
    from codeupipe.ai.providers.base import LanguageModelProvider

logger = logging.getLogger("codeupipe.ai.filters.init_provider")


class InitProviderLink:
    """Start a language model provider and place it on context.

    Args:
        provider: The provider instance to initialize.
            Must implement the LanguageModelProvider protocol.
    """

    def __init__(self, provider: LanguageModelProvider) -> None:
        self._provider = provider

    async def call(self, payload: Payload) -> Payload:
        mcp_servers = payload.get("mcp_servers") or {}

        await self._provider.start(mcp_servers=mcp_servers)

        logger.info("Provider initialized and placed on context")
        return payload.insert("provider", self._provider)
