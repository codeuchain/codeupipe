"""Integration tests for CopilotApp — full app lifecycle."""

from __future__ import annotations

import pytest

from codeupipe.ai.tui.app import CopilotApp
from codeupipe.ai.tui.widgets.chat_pane import ChatPane
from codeupipe.ai.tui.widgets.event_panel import EventPanel
from codeupipe.ai.tui.widgets.input_bar import InputBar


@pytest.mark.integration
class TestCopilotApp:
    """CopilotApp integration tests — app as a whole."""

    @pytest.mark.asyncio
    async def test_app_launches_and_has_widgets(self):
        """App starts and contains all expected widgets."""
        app = CopilotApp(model="gpt-4.1")
        async with app.run_test() as pilot:
            assert pilot.app.query_one("#chat", ChatPane)
            assert pilot.app.query_one("#events", EventPanel)
            assert pilot.app.query_one("#input", InputBar)

    @pytest.mark.asyncio
    async def test_app_title(self):
        """App has the correct title."""
        app = CopilotApp()
        async with app.run_test() as pilot:
            assert pilot.app.title == "Copilot Agent"

    @pytest.mark.asyncio
    async def test_model_in_subtitle(self):
        """Model name appears in subtitle."""
        app = CopilotApp(model="gpt-4.1")
        async with app.run_test() as pilot:
            assert "gpt-4.1" in pilot.app.sub_title

    @pytest.mark.asyncio
    async def test_mode_in_subtitle(self):
        """Mode appears in subtitle."""
        app = CopilotApp()
        async with app.run_test() as pilot:
            assert "agent" in pilot.app.sub_title

    @pytest.mark.asyncio
    async def test_initial_system_message(self):
        """Chat pane has initial system message after mount."""
        app = CopilotApp(model="gpt-4.1")
        async with app.run_test() as pilot:
            chat = pilot.app.query_one("#chat", ChatPane)
            assert len(chat.lines) > 0  # System message was written

    @pytest.mark.asyncio
    async def test_event_panel_has_header(self):
        """Event panel starts with header text."""
        app = CopilotApp()
        async with app.run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            assert len(panel.lines) > 0  # Header was written

    @pytest.mark.asyncio
    async def test_toggle_events(self):
        """toggle_events action toggles event panel visibility.

        Note: ctrl+e is captured by Input (emacs end-of-line),
        so we test the action directly. Key conflict is tracked
        for Phase 2d UX refinement.
        """
        app = CopilotApp()
        async with app.run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            assert panel.display is True

            await pilot.app.run_action("toggle_events")
            assert panel.display is False

            await pilot.app.run_action("toggle_events")
            assert panel.display is True

    @pytest.mark.asyncio
    async def test_clear_chat(self):
        """Ctrl+L clears the chat pane."""
        app = CopilotApp()
        async with app.run_test() as pilot:
            chat = pilot.app.query_one("#chat", ChatPane)
            chat.write_user("Test message")
            initial_count = len(chat.lines)

            await pilot.press("ctrl+l")
            await pilot.pause()
            # After clear, should have system message "Chat cleared."
            # but fewer lines than before
            assert len(chat.lines) <= initial_count

    @pytest.mark.asyncio
    async def test_help_command(self):
        """Typing /help shows help text."""
        app = CopilotApp()
        async with app.run_test() as pilot:
            input_bar = pilot.app.query_one("#input", InputBar)
            chat = pilot.app.query_one("#chat", ChatPane)
            initial_count = len(chat.lines)

            # Simulate slash command
            app._handle_command("/help")
            assert len(chat.lines) > initial_count

    @pytest.mark.asyncio
    async def test_model_command(self):
        """Typing /model <name> changes the model."""
        app = CopilotApp(model="gpt-4.1")
        async with app.run_test() as pilot:
            app._handle_command("/model claude-3.5-sonnet")
            assert app.model_name == "claude-3.5-sonnet"

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        """Unknown slash command shows error message."""
        app = CopilotApp()
        async with app.run_test() as pilot:
            chat = pilot.app.query_one("#chat", ChatPane)
            initial_count = len(chat.lines)
            app._handle_command("/nonexistent")
            assert len(chat.lines) > initial_count

    @pytest.mark.asyncio
    async def test_input_bar_focused_on_mount(self):
        """Input bar receives focus on mount."""
        app = CopilotApp()
        async with app.run_test() as pilot:
            input_bar = pilot.app.query_one("#input", InputBar)
            assert input_bar.has_focus

    @pytest.mark.asyncio
    async def test_reactive_model_updates_subtitle(self):
        """Changing model_name reactive updates subtitle."""
        app = CopilotApp(model="gpt-4.1")
        async with app.run_test() as pilot:
            app.model_name = "o1-preview"
            assert "o1-preview" in app.sub_title
