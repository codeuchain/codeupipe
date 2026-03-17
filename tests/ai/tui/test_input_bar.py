"""Unit tests for InputBar widget."""

from __future__ import annotations

import pytest

from textual.app import App, ComposeResult

from codeupipe.ai.tui.widgets.input_bar import InputBar, SLASH_COMMANDS


class InputBarApp(App):
    """Minimal app for testing InputBar in isolation."""

    def compose(self) -> ComposeResult:
        yield InputBar(id="input")


@pytest.mark.unit
class TestInputBar:
    """InputBar widget tests — isolated."""

    @pytest.mark.asyncio
    async def test_input_bar_mounts(self):
        """InputBar renders and can be queried."""
        async with InputBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#input", InputBar)
            assert bar is not None

    @pytest.mark.asyncio
    async def test_default_mode_is_agent(self):
        """Default mode is 'agent'."""
        async with InputBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#input", InputBar)
            assert bar.mode == "agent"

    @pytest.mark.asyncio
    async def test_cycle_mode(self):
        """cycle_mode() toggles between agent and ask."""
        async with InputBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#input", InputBar)
            assert bar.mode == "agent"

            new_mode = bar.cycle_mode()
            assert new_mode == "ask"
            assert bar.mode == "ask"

            new_mode = bar.cycle_mode()
            assert new_mode == "agent"
            assert bar.mode == "agent"

    @pytest.mark.asyncio
    async def test_placeholder_text(self):
        """Input has the expected placeholder."""
        async with InputBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#input", InputBar)
            assert "/" in bar.placeholder
            assert "@" in bar.placeholder

    @pytest.mark.asyncio
    async def test_history_navigation(self):
        """History back/forward navigates through submitted inputs."""
        async with InputBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#input", InputBar)

            # Simulate submitting entries directly via history
            bar._history = ["first", "second", "third"]
            bar._history_index = -1

            bar.history_back()
            assert bar.value == "third"

            bar.history_back()
            assert bar.value == "second"

            bar.history_forward()
            assert bar.value == "third"

            bar.history_forward()
            assert bar.value == ""

    @pytest.mark.asyncio
    async def test_empty_history_no_crash(self):
        """history_back on empty history doesn't crash."""
        async with InputBarApp().run_test() as pilot:
            bar = pilot.app.query_one("#input", InputBar)
            bar.history_back()  # Should not raise
            bar.history_forward()  # Should not raise

    @pytest.mark.asyncio
    async def test_slash_commands_defined(self):
        """SLASH_COMMANDS contains expected commands."""
        assert "/help" in SLASH_COMMANDS
        assert "/clear" in SLASH_COMMANDS
        assert "/exit" in SLASH_COMMANDS
