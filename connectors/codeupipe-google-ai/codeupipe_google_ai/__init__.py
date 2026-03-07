"""
codeupipe-google-ai: Google AI (Gemini) connector package.

Filters:
- GeminiGenerate: Text generation / chat (sync)
- GeminiGenerateStream: Streaming generation via StreamFilter
- GeminiEmbed: Text embeddings
- GeminiVision: Image/video/PDF analysis
"""

from .generate import GeminiGenerate
from .generate_stream import GeminiGenerateStream
from .embed import GeminiEmbed
from .vision import GeminiVision


def register(registry, config):
    """Entry point called by codeupipe discover_connectors."""
    from google import genai

    api_key = config.resolve_env("api_key_env")
    client = genai.Client(api_key=api_key)
    model = config.get("model", "gemini-2.0-flash")

    registry.register(
        f"{config.name}_generate",
        lambda: GeminiGenerate(client=client, model=model),
        kind="connector",
        force=True,
    )
    registry.register(
        f"{config.name}_generate_stream",
        lambda: GeminiGenerateStream(client=client, model=model),
        kind="connector",
        force=True,
    )

    embed_model = config.get("embed_model", "gemini-embedding-001")
    registry.register(
        f"{config.name}_embed",
        lambda: GeminiEmbed(client=client, model=embed_model),
        kind="connector",
        force=True,
    )
    registry.register(
        f"{config.name}_vision",
        lambda: GeminiVision(client=client, model=model),
        kind="connector",
        force=True,
    )


__all__ = [
    "register",
    "GeminiGenerate",
    "GeminiGenerateStream",
    "GeminiEmbed",
    "GeminiVision",
]
