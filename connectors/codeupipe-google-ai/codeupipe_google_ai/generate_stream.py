"""
GeminiGenerateStream: Streaming text generation via Gemini.

Yields chunks as they arrive from the Gemini streaming API.
Each chunk payload contains 'chunk_text' and 'chunk_index'.
"""

from typing import AsyncIterator

from codeupipe import Payload


class GeminiGenerateStream:
    """Streaming generation — yields one payload per chunk."""

    def __init__(self, client, model: str = "gemini-2.0-flash"):
        self._client = client
        self._model = model

    async def stream(self, payload: Payload) -> AsyncIterator[Payload]:
        prompt = payload.get("prompt", "")
        system_instruction = payload.get("system_instruction", None)

        config_kwargs = {}
        if system_instruction is not None:
            config_kwargs["system_instruction"] = system_instruction

        from google.genai import types

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        response = self._client.models.generate_content_stream(
            model=self._model,
            contents=prompt,
            config=config,
        )

        idx = 0
        for chunk in response:
            text = chunk.text if chunk.text else ""
            yield payload.insert("chunk_text", text).insert("chunk_index", idx)
            idx += 1
