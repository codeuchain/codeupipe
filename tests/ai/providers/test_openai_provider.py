"""RED PHASE — Tests for OpenAICompatibleProvider.

OpenAICompatibleProvider talks to any OpenAI-compatible chat/completions
endpoint (OpenAI, Groq, Together, Ollama, LM Studio, etc.) via urllib.
Zero external dependencies.

Tests mock urllib to verify HTTP shape and response normalization.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from codeupipe.ai.providers.base import ModelResponse, ToolCall
from codeupipe.ai.providers.openai_compat import OpenAICompatibleProvider


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def provider() -> OpenAICompatibleProvider:
    """Standard OpenAI-compatible provider."""
    return OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk-test-key",
        model="gpt-4.1",
    )


@pytest.fixture()
def ollama_provider() -> OpenAICompatibleProvider:
    """Ollama provider (no API key needed)."""
    return OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        api_key="",
        model="llama3",
    )


def _mock_response(data: dict, status: int = 200):
    """Create a mock urllib response."""
    body = json.dumps(data).encode("utf-8")
    mock = MagicMock()
    mock.status = status
    mock.read.return_value = body
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


# ── Lifecycle ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_is_noop(self, provider: OpenAICompatibleProvider):
        """start() should succeed without errors (HTTP is stateless)."""
        await provider.start()

    @pytest.mark.asyncio
    async def test_stop_is_noop(self, provider: OpenAICompatibleProvider):
        """stop() should succeed without errors."""
        await provider.stop()

    @pytest.mark.asyncio
    async def test_send_without_start_works(self, provider: OpenAICompatibleProvider):
        """HTTP provider doesn't need explicit start()."""
        response_data = {
            "choices": [{
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)):
            result = await provider.send("Hi")
        assert result.content == "Hello!"


# ── Request Shape ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestRequestShape:
    """Tests verifying the outgoing HTTP request format."""

    @pytest.mark.asyncio
    async def test_posts_to_chat_completions(self, provider: OpenAICompatibleProvider):
        """Request goes to {base_url}/chat/completions."""
        response_data = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)) as mock_open:
            await provider.send("test")
            call_args = mock_open.call_args
            req = call_args[0][0]
            assert "/chat/completions" in req.full_url

    @pytest.mark.asyncio
    async def test_sends_authorization_header(self, provider: OpenAICompatibleProvider):
        """Request includes Authorization: Bearer header."""
        response_data = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)) as mock_open:
            await provider.send("test")
            req = mock_open.call_args[0][0]
            assert req.get_header("Authorization") == "Bearer sk-test-key"

    @pytest.mark.asyncio
    async def test_no_auth_header_when_no_key(self, ollama_provider: OpenAICompatibleProvider):
        """Omit Authorization header when api_key is empty."""
        response_data = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)) as mock_open:
            await ollama_provider.send("test")
            req = mock_open.call_args[0][0]
            assert req.get_header("Authorization") is None

    @pytest.mark.asyncio
    async def test_request_body_shape(self, provider: OpenAICompatibleProvider):
        """Request body has model, messages, temperature."""
        response_data = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)) as mock_open:
            await provider.send("Hello")
            req = mock_open.call_args[0][0]
            body = json.loads(req.data)
            assert body["model"] == "gpt-4.1"
            assert body["messages"][-1]["content"] == "Hello"
            assert body["messages"][-1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_system_prompt_included(self):
        """If system_prompt is set, it's the first message."""
        provider = OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4.1",
            system_prompt="You are a helpful assistant.",
        )
        response_data = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)) as mock_open:
            await provider.send("Hi")
            req = mock_open.call_args[0][0]
            body = json.loads(req.data)
            assert body["messages"][0]["role"] == "system"
            assert body["messages"][0]["content"] == "You are a helpful assistant."


# ── Response Normalization ────────────────────────────────────────────


@pytest.mark.unit
class TestResponseNormalization:
    """Tests verifying ModelResponse normalization."""

    @pytest.mark.asyncio
    async def test_text_response(self, provider: OpenAICompatibleProvider):
        """Standard text response is normalized to ModelResponse."""
        response_data = {
            "choices": [{
                "message": {"role": "assistant", "content": "The answer is 42."},
                "finish_reason": "stop",
            }],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)):
            result = await provider.send("What is the answer?")
        assert isinstance(result, ModelResponse)
        assert result.content == "The answer is 42."
        assert result.tool_calls == ()

    @pytest.mark.asyncio
    async def test_empty_content(self, provider: OpenAICompatibleProvider):
        """Response with null content."""
        response_data = {
            "choices": [{
                "message": {"role": "assistant", "content": None},
                "finish_reason": "stop",
            }],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)):
            result = await provider.send("test")
        assert result.content is None

    @pytest.mark.asyncio
    async def test_raw_preserved(self, provider: OpenAICompatibleProvider):
        """The raw API response dict is preserved on ModelResponse."""
        response_data = {
            "id": "chatcmpl-abc",
            "choices": [{
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": "stop",
            }],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)):
            result = await provider.send("test")
        assert result.raw["id"] == "chatcmpl-abc"


# ── Tool Calls ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestToolCalls:
    """Tests for tool call extraction."""

    @pytest.mark.asyncio
    async def test_tool_calls_extracted(self, provider: OpenAICompatibleProvider):
        """Tool calls from the response are extracted as ToolCall objects."""
        response_data = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city": "Seattle"}',
                            },
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)):
            result = await provider.send("What's the weather?")
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert isinstance(tc, ToolCall)
        assert tc.id == "call_123"
        assert tc.name == "get_weather"
        assert tc.arguments == '{"city": "Seattle"}'

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, provider: OpenAICompatibleProvider):
        """Multiple tool calls in a single response."""
        response_data = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "tool_a", "arguments": "{}"},
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {"name": "tool_b", "arguments": "{}"},
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)):
            result = await provider.send("Do both")
        assert len(result.tool_calls) == 2

    @pytest.mark.asyncio
    async def test_no_tool_calls_field(self, provider: OpenAICompatibleProvider):
        """Response without tool_calls field returns empty tuple."""
        response_data = {
            "choices": [{
                "message": {"role": "assistant", "content": "just text"},
                "finish_reason": "stop",
            }],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)):
            result = await provider.send("test")
        assert result.tool_calls == ()


# ── Conversation History ──────────────────────────────────────────────


@pytest.mark.unit
class TestConversationHistory:
    """Tests for multi-turn conversation support."""

    @pytest.mark.asyncio
    async def test_history_accumulates(self, provider: OpenAICompatibleProvider):
        """Each send adds user + assistant messages to history."""
        response_data = {
            "choices": [{"message": {"content": "First"}, "finish_reason": "stop"}],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)):
            await provider.send("Hello")

        response_data2 = {
            "choices": [{"message": {"content": "Second"}, "finish_reason": "stop"}],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data2)) as mock_open:
            await provider.send("Follow up")
            req = mock_open.call_args[0][0]
            body = json.loads(req.data)
            # Should have: [user: Hello, assistant: First, user: Follow up]
            messages = body["messages"]
            assert len(messages) >= 3
            assert messages[-3]["content"] == "Hello"
            assert messages[-2]["content"] == "First"
            assert messages[-1]["content"] == "Follow up"

    @pytest.mark.asyncio
    async def test_clear_history(self, provider: OpenAICompatibleProvider):
        """clear_history resets conversation state."""
        response_data = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        }
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)):
            await provider.send("Hello")
        provider.clear_history()
        with patch("urllib.request.urlopen", return_value=_mock_response(response_data)) as mock_open:
            await provider.send("Fresh start")
            body = json.loads(mock_open.call_args[0][0].data)
            user_msgs = [m for m in body["messages"] if m["role"] == "user"]
            assert len(user_msgs) == 1


# ── Error Handling ────────────────────────────────────────────────────


@pytest.mark.unit
class TestErrorHandling:
    """Tests for error scenarios."""

    @pytest.mark.asyncio
    async def test_http_error_raises(self, provider: OpenAICompatibleProvider):
        """HTTP errors surface as RuntimeError."""
        import urllib.error
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                "https://api.openai.com/v1/chat/completions",
                429, "Rate limited", {}, None,
            ),
        ):
            with pytest.raises(RuntimeError, match="429"):
                await provider.send("test")
