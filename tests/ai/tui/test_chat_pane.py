"""Unit tests for ChatPane widget."""

from __future__ import annotations

import pytest

from textual.app import App, ComposeResult

from codeupipe.ai.tui.widgets.chat_pane import ChatPane


class ChatPaneApp(App):
    """Minimal app for testing ChatPane in isolation."""

    def compose(self) -> ComposeResult:
        yield ChatPane(id="chat")


@pytest.mark.unit
class TestChatPane:
    """ChatPane widget tests — isolated."""

    @pytest.mark.asyncio
    async def test_chat_pane_mounts(self):
        """ChatPane renders and can be queried."""
        async with ChatPaneApp().run_test() as pilot:
            chat = pilot.app.query_one("#chat", ChatPane)
            assert chat is not None

    @pytest.mark.asyncio
    async def test_write_user_message(self):
        """write_user() appends styled text to the log."""
        async with ChatPaneApp().run_test() as pilot:
            chat = pilot.app.query_one("#chat", ChatPane)
            chat.write_user("Hello, agent!")
            # RichLog tracks lines written — verify it has content
            assert len(chat.lines) > 0

    @pytest.mark.asyncio
    async def test_write_agent_message(self):
        """write_agent() renders markdown into the log."""
        async with ChatPaneApp().run_test() as pilot:
            chat = pilot.app.query_one("#chat", ChatPane)
            chat.write_agent("**Bold** response with `code`.")
            assert len(chat.lines) > 0

    @pytest.mark.asyncio
    async def test_write_error(self):
        """write_error() appends red error text."""
        async with ChatPaneApp().run_test() as pilot:
            chat = pilot.app.query_one("#chat", ChatPane)
            chat.write_error("Something went wrong")
            assert len(chat.lines) > 0

    @pytest.mark.asyncio
    async def test_write_system(self):
        """write_system() appends dim system text."""
        async with ChatPaneApp().run_test() as pilot:
            chat = pilot.app.query_one("#chat", ChatPane)
            chat.write_system("System message")
            assert len(chat.lines) > 0

    @pytest.mark.asyncio
    async def test_streaming_begin_end(self):
        """begin_agent/stream_token/end_agent lifecycle works."""
        async with ChatPaneApp().run_test() as pilot:
            chat = pilot.app.query_one("#chat", ChatPane)
            initial = len(chat.lines)

            chat.begin_agent()
            assert chat._streaming is True

            chat.stream_token("Hello ")
            chat.stream_token("world")
            assert len(chat._stream_buffer) == 2

            chat.end_agent()
            assert chat._streaming is False
            assert len(chat._stream_buffer) == 0
            assert len(chat.lines) > initial
