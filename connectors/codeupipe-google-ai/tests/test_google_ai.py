"""
Unit tests for codeupipe-google-ai connector.

All tests mock the google-genai SDK — no API key needed.
Uses sys.modules mocking since google-genai is not installed in test env.
"""

import asyncio
import sys
from types import SimpleNamespace, ModuleType
from unittest.mock import MagicMock

import pytest

from codeupipe import Payload


# ── Module-level mocks for google.genai ─────────────────────────────

_mock_google = ModuleType("google")
_mock_genai = ModuleType("google.genai")
_mock_types = ModuleType("google.genai.types")

_mock_types.GenerateContentConfig = MagicMock()
_mock_types.Part = MagicMock()

_mock_genai.types = _mock_types
_mock_google.genai = _mock_genai


@pytest.fixture(autouse=True)
def mock_google_modules():
    """Inject mock google modules into sys.modules for all tests."""
    originals = {}
    for mod_name in ("google", "google.genai", "google.genai.types"):
        originals[mod_name] = sys.modules.get(mod_name)

    sys.modules["google"] = _mock_google
    sys.modules["google.genai"] = _mock_genai
    sys.modules["google.genai.types"] = _mock_types

    _mock_types.GenerateContentConfig.reset_mock()
    _mock_types.Part.reset_mock()

    yield

    for mod_name, orig in originals.items():
        if orig is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = orig

    for key in list(sys.modules):
        if key.startswith("codeupipe_google_ai"):
            del sys.modules[key]


# ── Mock helpers ────────────────────────────────────────────────────


def make_mock_client():
    client = MagicMock()
    response = SimpleNamespace(text="Hello from Gemini")
    client.models.generate_content.return_value = response

    chunk1 = SimpleNamespace(text="Hello ")
    chunk2 = SimpleNamespace(text="world")
    client.models.generate_content_stream.return_value = [chunk1, chunk2]

    emb = SimpleNamespace(values=[0.1, 0.2, 0.3])
    embed_response = SimpleNamespace(embeddings=[emb])
    client.models.embed_content.return_value = embed_response

    return client


# ── GeminiGenerate ──────────────────────────────────────────────────


class TestGeminiGenerate:
    def test_basic_generation(self):
        from codeupipe_google_ai.generate import GeminiGenerate

        client = make_mock_client()
        f = GeminiGenerate(client=client, model="gemini-2.0-flash")
        payload = Payload({"prompt": "Say hello"})
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))
        assert result.get("response") == "Hello from Gemini"
        client.models.generate_content.assert_called_once()

    def test_passes_model(self):
        from codeupipe_google_ai.generate import GeminiGenerate

        client = make_mock_client()
        f = GeminiGenerate(client=client, model="gemini-3-pro-preview")
        payload = Payload({"prompt": "Test"})
        asyncio.get_event_loop().run_until_complete(f.call(payload))
        call_kwargs = client.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemini-3-pro-preview"

    def test_config_params_forwarded(self):
        from codeupipe_google_ai.generate import GeminiGenerate

        client = make_mock_client()
        f = GeminiGenerate(client=client)
        payload = Payload({
            "prompt": "Hi",
            "temperature": 0.5,
            "max_output_tokens": 100,
            "system_instruction": "Be brief",
        })
        asyncio.get_event_loop().run_until_complete(f.call(payload))
        _mock_types.GenerateContentConfig.assert_called_once_with(
            system_instruction="Be brief",
            temperature=0.5,
            max_output_tokens=100,
        )

    def test_no_config_when_no_params(self):
        from codeupipe_google_ai.generate import GeminiGenerate

        client = make_mock_client()
        f = GeminiGenerate(client=client)
        payload = Payload({"prompt": "Simple"})
        asyncio.get_event_loop().run_until_complete(f.call(payload))
        call_kwargs = client.models.generate_content.call_args
        assert call_kwargs.kwargs["config"] is None


# ── GeminiGenerateStream ───────────────────────────────────────────


class TestGeminiGenerateStream:
    def test_yields_chunks(self):
        from codeupipe_google_ai.generate_stream import GeminiGenerateStream

        client = make_mock_client()
        f = GeminiGenerateStream(client=client)
        payload = Payload({"prompt": "Stream test"})

        async def collect():
            chunks = []
            async for chunk in f.stream(payload):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.get_event_loop().run_until_complete(collect())
        assert len(chunks) == 2
        assert chunks[0].get("chunk_text") == "Hello "
        assert chunks[0].get("chunk_index") == 0
        assert chunks[1].get("chunk_text") == "world"
        assert chunks[1].get("chunk_index") == 1


# ── GeminiEmbed ─────────────────────────────────────────────────────


class TestGeminiEmbed:
    def test_returns_embeddings(self):
        from codeupipe_google_ai.embed import GeminiEmbed

        client = make_mock_client()
        f = GeminiEmbed(client=client)
        payload = Payload({"text": "Hello world"})
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))
        embeddings = result.get("embeddings")
        assert len(embeddings) == 1
        assert embeddings[0] == [0.1, 0.2, 0.3]

    def test_uses_configured_model(self):
        from codeupipe_google_ai.embed import GeminiEmbed

        client = make_mock_client()
        f = GeminiEmbed(client=client, model="custom-embed")
        payload = Payload({"text": "test"})
        asyncio.get_event_loop().run_until_complete(f.call(payload))
        call_kwargs = client.models.embed_content.call_args
        assert call_kwargs.kwargs["model"] == "custom-embed"


# ── GeminiVision ────────────────────────────────────────────────────


class TestGeminiVision:
    def test_vision_with_bytes(self):
        from codeupipe_google_ai.vision import GeminiVision

        client = make_mock_client()
        _mock_types.Part.from_text.return_value = "text_part"
        _mock_types.Part.from_bytes.return_value = "image_part"

        f = GeminiVision(client=client)
        payload = Payload({
            "prompt": "What's in this image?",
            "image_bytes": b"\x89PNG\r\n",
            "mime_type": "image/png",
        })
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))
        assert result.get("response") == "Hello from Gemini"
        _mock_types.Part.from_bytes.assert_called_once()

    def test_vision_with_file_path(self, tmp_path):
        from codeupipe_google_ai.vision import GeminiVision

        client = make_mock_client()
        _mock_types.Part.from_text.return_value = "text_part"
        _mock_types.Part.from_bytes.return_value = "image_part"

        f = GeminiVision(client=client)
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0")
        payload = Payload({
            "prompt": "Describe",
            "image_path": str(img),
        })
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))
        assert result.get("response") == "Hello from Gemini"


# ── register entry point ────────────────────────────────────────────


class TestRegister:
    def test_register_creates_four_entries(self):
        from codeupipe.registry import Registry
        from codeupipe.connect.config import ConnectorConfig

        registry = Registry()
        config = ConnectorConfig(
            name="gemini",
            provider="google-ai",
            raw={
                "provider": "google-ai",
                "api_key_env": "GOOGLE_API_KEY",
                "model": "gemini-2.0-flash",
            },
        )

        import os
        os.environ["GOOGLE_API_KEY"] = "test-key-fake"
        try:
            _mock_genai.Client = MagicMock(return_value=make_mock_client())
            from codeupipe_google_ai import register
            register(registry, config)
        finally:
            os.environ.pop("GOOGLE_API_KEY", None)

        names = registry.list()
        assert "gemini_generate" in names
        assert "gemini_generate_stream" in names
        assert "gemini_embed" in names
        assert "gemini_vision" in names
