"""
GeminiEmbed: Text embeddings via Gemini embedding model.

Reads 'text' (str or list of str) from payload, returns 'embeddings'.
"""

from codeupipe import Payload


class GeminiEmbed:
    """Generate text embeddings using Gemini embedding model."""

    def __init__(self, client, model: str = "gemini-embedding-001"):
        self._client = client
        self._model = model

    async def call(self, payload: Payload) -> Payload:
        text = payload.get("text", "")

        response = self._client.models.embed_content(
            model=self._model,
            contents=text,
        )

        embeddings = [e.values for e in response.embeddings]
        return payload.insert("embeddings", embeddings)
