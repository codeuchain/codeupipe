"""OpenAICompatibleProvider — HTTP-based provider for OpenAI-compatible APIs.

Works with any endpoint that implements the OpenAI chat/completions API:
  - OpenAI (api.openai.com/v1)
  - Groq (api.groq.com/openai/v1)
  - Together AI (api.together.xyz/v1)
  - Ollama (localhost:11434/v1)
  - LM Studio (localhost:1234/v1)
  - Fireworks, DeepSeek, Cerebras, etc.

Zero external dependencies — uses urllib from stdlib.
Stateless HTTP — start()/stop() are no-ops.

Lifecycle:
    provider = OpenAICompatibleProvider(base_url=..., api_key=..., model=...)
    await provider.start()    # no-op (HTTP is stateless)
    response = await provider.send("Hello")
    await provider.stop()     # no-op
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from codeupipe.ai.providers.base import ModelResponse, ToolCall

logger = logging.getLogger("codeupipe.ai.providers.openai_compat")

__all__ = ["OpenAICompatibleProvider"]


class OpenAICompatibleProvider:
    """Language model provider for OpenAI-compatible chat/completions APIs.

    Args:
        base_url: API base URL (e.g. "https://api.openai.com/v1").
                  Trailing slash is stripped automatically.
        api_key: API key / bearer token. Empty string for local models.
        model: Model identifier (e.g. "gpt-4.1", "llama3").
        system_prompt: Optional system message prepended to every request.
        temperature: Sampling temperature (default 0.7).
        max_tokens: Maximum response tokens (None = provider default).
        extra_headers: Additional HTTP headers for every request.
        extra_body: Additional fields merged into every request body.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._extra_headers = extra_headers or {}
        self._extra_body = extra_body or {}
        self._history: list[dict[str, str]] = []

    # ── LanguageModelProvider protocol ────────────────────────────────

    async def start(self, **kwargs: Any) -> None:
        """No-op — HTTP is stateless."""
        logger.info(
            "OpenAICompatibleProvider ready (base_url=%s, model=%s)",
            self._base_url, self._model,
        )

    async def send(self, prompt: str) -> ModelResponse:
        """Send a prompt to the chat/completions endpoint.

        Maintains conversation history across calls. Use clear_history()
        to reset between conversations.

        Args:
            prompt: User message to send.

        Returns:
            Normalized ModelResponse.

        Raises:
            RuntimeError: On HTTP errors.
        """
        # Build messages
        messages: list[dict[str, str]] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.extend(self._history)
        messages.append({"role": "user", "content": prompt})

        # Build request body
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
        }
        if self._max_tokens is not None:
            body["max_tokens"] = self._max_tokens
        body.update(self._extra_body)

        # Make the request
        raw_response = self._do_request(body)

        # Parse response
        choice = raw_response.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = message.get("content")
        tool_calls = self._extract_tool_calls(message)

        # Update history
        self._history.append({"role": "user", "content": prompt})
        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if content:
            assistant_msg["content"] = content
        self._history.append(assistant_msg)

        return ModelResponse(
            content=content,
            tool_calls=tuple(tool_calls),
            raw=raw_response,
        )

    async def stop(self) -> None:
        """No-op — HTTP is stateless."""
        self._history.clear()

    # ── Public helpers ────────────────────────────────────────────────

    def clear_history(self) -> None:
        """Reset conversation history for a fresh conversation."""
        self._history.clear()

    @property
    def model(self) -> str:
        """The model identifier."""
        return self._model

    @property
    def base_url(self) -> str:
        """The API base URL."""
        return self._base_url

    # ── Internals ─────────────────────────────────────────────────────

    def _do_request(self, body: dict[str, Any]) -> dict[str, Any]:
        """Execute the HTTP request to chat/completions."""
        url = f"{self._base_url}/chat/completions"
        data = json.dumps(body).encode("utf-8")

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(self._extra_headers)

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = ""
            if exc.fp:
                try:
                    body_text = exc.fp.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
            raise RuntimeError(
                f"OpenAI API error {exc.code}: {exc.reason}\n{body_text}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Failed to connect to {url}: {exc.reason}"
            ) from exc

    @staticmethod
    def _extract_tool_calls(message: dict[str, Any]) -> list[ToolCall]:
        """Extract ToolCall objects from an assistant message."""
        raw_calls = message.get("tool_calls")
        if not raw_calls:
            return []

        calls: list[ToolCall] = []
        for tc in raw_calls:
            fn = tc.get("function", {})
            calls.append(ToolCall(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=fn.get("arguments", "{}"),
            ))
        return calls
