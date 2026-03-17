"""Tests for the Echo MCP sub-server.

Unit tests verify the tool functions directly — no MCP transport needed.
"""

import pytest

from codeupipe.ai.servers.echo import echo_message, echo_reverse, echo_upper


@pytest.mark.unit
class TestEchoServer:
    """Unit tests for echo server tools."""

    @pytest.mark.asyncio
    async def test_echo_message(self):
        """echo_message returns the message prefixed with 'Echo: '."""
        result = await echo_message("hello")
        assert result == "Echo: hello"

    @pytest.mark.asyncio
    async def test_echo_message_empty(self):
        """echo_message handles empty string."""
        result = await echo_message("")
        assert result == "Echo: "

    @pytest.mark.asyncio
    async def test_echo_reverse(self):
        """echo_reverse returns the message reversed."""
        result = await echo_reverse("hello")
        assert result == "Echo: olleh"

    @pytest.mark.asyncio
    async def test_echo_upper(self):
        """echo_upper returns the message uppercased."""
        result = await echo_upper("hello")
        assert result == "Echo: HELLO"
