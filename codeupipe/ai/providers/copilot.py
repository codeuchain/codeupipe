"""CopilotProvider — Copilot SDK implementation of LanguageModelProvider.

Wraps CopilotClient + CopilotSession behind the provider interface.
All SDK-specific logic is contained here; nothing leaks upstream.

Lifecycle:
    start(mcp_servers=...)  → CopilotClient().start() + create_session()
    send(prompt)            → session.send_and_wait({"prompt": ...})
    stop()                  → session.destroy() + client.stop()
"""

from __future__ import annotations

import logging
from typing import Any

from codeupipe.ai.providers.base import LanguageModelProvider, ModelResponse

logger = logging.getLogger("codeupipe.ai.providers.copilot")


class CopilotProvider:
    """Copilot SDK adapter for LanguageModelProvider.

    Args:
        model: Model identifier (default: "gpt-4.1").
        client_options: Options dict passed to CopilotClient constructor.
    """

    def __init__(
        self,
        *,
        model: str = "gpt-4.1",
        client_options: dict[str, Any] | None = None,
    ) -> None:
        self._model = model
        self._client_options = client_options or {}
        self._client: Any = None
        self._session: Any = None

    async def start(self, **kwargs: Any) -> None:
        """Initialize the Copilot client and create a session.

        Keyword Args:
            mcp_servers: Dict of MCP server configurations for the session.
        """
        from copilot import CopilotClient

        mcp_servers = kwargs.get("mcp_servers") or {}

        self._client = CopilotClient(self._client_options)
        await self._client.start()

        session_config: dict[str, Any] = {
            "model": self._model,
            "mcp_servers": mcp_servers,
        }

        self._session = await self._client.create_session(session_config)

        logger.info(
            "CopilotProvider started (model=%s, mcp_servers=%d)",
            self._model,
            len(mcp_servers),
        )

    async def send(self, prompt: str) -> ModelResponse:
        """Send a prompt to the Copilot session and return normalized response.

        The Copilot SDK's send_and_wait handles the full tool loop
        internally (model requests tool → SDK executes → feeds back →
        model continues until end_turn). By the time it returns, all
        tool calls are complete.

        Args:
            prompt: The prompt string to send.

        Returns:
            ModelResponse with extracted content and tool results.

        Raises:
            RuntimeError: If start() has not been called.
        """
        if not self._session:
            raise RuntimeError(
                "CopilotProvider not started. Call start() before send()."
            )

        event = await self._session.send_and_wait({"prompt": prompt})

        content = None
        tool_results: list[dict] = []

        if event is not None and hasattr(event, "data"):
            data = event.data
            if data is not None:
                content = getattr(data, "content", None)

                # Extract tool results for downstream links
                if hasattr(data, "tool_results") and data.tool_results:
                    tool_results = [
                        r for r in data.tool_results if isinstance(r, dict)
                    ]

        return ModelResponse(
            content=content,
            tool_results=tuple(tool_results),
            raw=event,
        )

    async def stop(self) -> None:
        """Destroy the session and stop the client."""
        if self._session:
            try:
                await self._session.destroy()
            except Exception:
                logger.warning("Error destroying Copilot session", exc_info=True)
            self._session = None

        if self._client:
            try:
                await self._client.stop()
            except Exception:
                logger.warning("Error stopping Copilot client", exc_info=True)
            self._client = None

        logger.info("CopilotProvider stopped")
