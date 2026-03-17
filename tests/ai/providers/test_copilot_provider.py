"""RED PHASE — Tests for CopilotProvider.

CopilotProvider wraps the Copilot SDK (CopilotClient + CopilotSession)
behind the LanguageModelProvider interface. Tests mock the SDK to
verify correct delegation and response normalization.
"""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codeupipe.ai.providers.base import ModelResponse
from codeupipe.ai.providers.copilot import CopilotProvider

_has_copilot = importlib.util.find_spec("copilot") is not None


@pytest.mark.unit
@pytest.mark.skipif(not _has_copilot, reason="copilot SDK not installed")
class TestCopilotProvider:
    """Unit tests for CopilotProvider."""

    @pytest.mark.asyncio
    async def test_start_creates_client_and_session(self):
        """start() creates CopilotClient, starts it, and creates session."""
        provider = CopilotProvider(model="gpt-4.1")

        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_client.create_session = AsyncMock(return_value=mock_session)

        with patch(
            "copilot.CopilotClient",
            return_value=mock_client,
        ):
            await provider.start(mcp_servers={"server1": {}})

        mock_client.start.assert_awaited_once()
        mock_client.create_session.assert_awaited_once_with({
            "model": "gpt-4.1",
            "mcp_servers": {"server1": {}},
        })

    @pytest.mark.asyncio
    async def test_start_default_mcp_servers(self):
        """start() with no mcp_servers uses empty dict."""
        provider = CopilotProvider()

        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_client.create_session = AsyncMock(return_value=MagicMock())

        with patch(
            "copilot.CopilotClient",
            return_value=mock_client,
        ):
            await provider.start()

        config = mock_client.create_session.call_args[0][0]
        assert config["mcp_servers"] == {}

    @pytest.mark.asyncio
    async def test_send_returns_model_response(self):
        """send() returns ModelResponse with normalized content."""
        provider = CopilotProvider()

        mock_event = MagicMock()
        mock_event.data.content = "Hello from the model!"

        mock_session = MagicMock()
        mock_session.send_and_wait = AsyncMock(return_value=mock_event)

        # Manually set session (bypassing start)
        provider._session = mock_session

        result = await provider.send("test prompt")

        assert isinstance(result, ModelResponse)
        assert result.content == "Hello from the model!"
        assert result.raw is mock_event
        mock_session.send_and_wait.assert_awaited_once_with(
            {"prompt": "test prompt"}
        )

    @pytest.mark.asyncio
    async def test_send_extracts_tool_results(self):
        """send() extracts tool_results from event.data."""
        provider = CopilotProvider()

        tool_data = [
            {"result": {"status": "ok"}, "__notifications__": []},
            {"result": {"data": 42}},
        ]
        mock_event = MagicMock()
        mock_event.data.content = "Done with tools"
        mock_event.data.tool_results = tool_data

        mock_session = MagicMock()
        mock_session.send_and_wait = AsyncMock(return_value=mock_event)
        provider._session = mock_session

        result = await provider.send("use tools")
        assert len(result.tool_results) == 2
        assert result.tool_results[0]["result"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_send_handles_none_event(self):
        """send() handles None return from send_and_wait (timeout)."""
        provider = CopilotProvider()

        mock_session = MagicMock()
        mock_session.send_and_wait = AsyncMock(return_value=None)
        provider._session = mock_session

        result = await provider.send("hello?")
        assert result.content is None
        assert result.tool_results == ()
        assert result.raw is None

    @pytest.mark.asyncio
    async def test_send_handles_none_data(self):
        """send() handles event with None data."""
        provider = CopilotProvider()

        mock_event = MagicMock()
        mock_event.data = None

        mock_session = MagicMock()
        mock_session.send_and_wait = AsyncMock(return_value=mock_event)
        provider._session = mock_session

        result = await provider.send("hello?")
        assert result.content is None

    @pytest.mark.asyncio
    async def test_send_raises_when_not_started(self):
        """send() raises RuntimeError if start() wasn't called."""
        provider = CopilotProvider()

        with pytest.raises(RuntimeError, match="not started"):
            await provider.send("test")

    @pytest.mark.asyncio
    async def test_stop_destroys_session_and_client(self):
        """stop() destroys session and stops client."""
        provider = CopilotProvider()

        mock_session = MagicMock()
        mock_session.destroy = AsyncMock()
        mock_client = MagicMock()
        mock_client.stop = AsyncMock()

        provider._session = mock_session
        provider._client = mock_client

        await provider.stop()

        mock_session.destroy.assert_awaited_once()
        mock_client.stop.assert_awaited_once()
        assert provider._session is None
        assert provider._client is None

    @pytest.mark.asyncio
    async def test_stop_handles_no_session(self):
        """stop() is safe to call when not started."""
        provider = CopilotProvider()
        await provider.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_stop_handles_destroy_error(self):
        """stop() continues cleanup even if session.destroy() fails."""
        provider = CopilotProvider()

        mock_session = MagicMock()
        mock_session.destroy = AsyncMock(side_effect=Exception("boom"))
        mock_client = MagicMock()
        mock_client.stop = AsyncMock()

        provider._session = mock_session
        provider._client = mock_client

        await provider.stop()  # Should not raise

        mock_client.stop.assert_awaited_once()
        assert provider._session is None

    @pytest.mark.asyncio
    async def test_client_options_passed_through(self):
        """client_options are forwarded to CopilotClient constructor."""
        opts = {"timeout": 30, "retries": 3}
        provider = CopilotProvider(client_options=opts)

        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_client.create_session = AsyncMock(return_value=MagicMock())

        with patch(
            "copilot.CopilotClient",
            return_value=mock_client,
        ) as mock_cls:
            await provider.start()

        mock_cls.assert_called_once_with(opts)

    @pytest.mark.asyncio
    async def test_send_ignores_non_dict_tool_results(self):
        """send() filters out non-dict items in tool_results."""
        provider = CopilotProvider()

        mock_event = MagicMock()
        mock_event.data.content = "done"
        mock_event.data.tool_results = [
            {"result": {"ok": True}},
            "not a dict",
            42,
            {"result": {"also": "ok"}},
        ]

        mock_session = MagicMock()
        mock_session.send_and_wait = AsyncMock(return_value=mock_event)
        provider._session = mock_session

        result = await provider.send("test")
        assert len(result.tool_results) == 2
