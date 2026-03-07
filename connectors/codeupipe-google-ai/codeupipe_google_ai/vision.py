"""
GeminiVision: Image/video/PDF analysis via Gemini multimodal.

Reads 'image_bytes' or 'image_path' + 'prompt' from payload,
returns 'response' with structured analysis text.
"""

from pathlib import Path

from codeupipe import Payload


class GeminiVision:
    """Multimodal vision analysis — images, video, PDFs."""

    def __init__(self, client, model: str = "gemini-2.0-flash"):
        self._client = client
        self._model = model

    async def call(self, payload: Payload) -> Payload:
        prompt = payload.get("prompt", "Describe this image.")

        from google.genai import types

        parts = [types.Part.from_text(text=prompt)]

        # Support raw bytes or file path
        image_bytes = payload.get("image_bytes", None)
        image_path = payload.get("image_path", None)
        mime_type = payload.get("mime_type", "image/jpeg")

        if image_bytes is not None:
            parts.append(
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            )
        elif image_path is not None:
            data = Path(image_path).read_bytes()
            parts.append(
                types.Part.from_bytes(data=data, mime_type=mime_type)
            )

        response = self._client.models.generate_content(
            model=self._model,
            contents=parts,
        )

        return payload.insert("response", response.text)
