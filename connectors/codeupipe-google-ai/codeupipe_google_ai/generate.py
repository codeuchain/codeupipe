"""
GeminiGenerate: Text generation / chat using Google AI Gemini.

Reads 'prompt' (and optional 'system_instruction', 'temperature',
'max_output_tokens') from the payload, returns 'response' text.
"""

from codeupipe import Payload


class GeminiGenerate:
    """Sync text generation via Gemini."""

    def __init__(self, client, model: str = "gemini-2.0-flash"):
        self._client = client
        self._model = model

    async def call(self, payload: Payload) -> Payload:
        prompt = payload.get("prompt", "")
        system_instruction = payload.get("system_instruction", None)
        temperature = payload.get("temperature", None)
        max_tokens = payload.get("max_output_tokens", None)

        config_kwargs = {}
        if system_instruction is not None:
            config_kwargs["system_instruction"] = system_instruction
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens

        from google.genai import types

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )

        return payload.insert("response", response.text)
