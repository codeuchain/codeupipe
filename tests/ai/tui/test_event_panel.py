"""Unit tests for EventPanel widget."""

from __future__ import annotations

import pytest

from textual.app import App, ComposeResult

from codeupipe.ai.tui.widgets.event_panel import EventPanel
from codeupipe.ai.agent.events import AgentEvent, EventType


class EventPanelApp(App):
    """Minimal app for testing EventPanel in isolation."""

    def compose(self) -> ComposeResult:
        yield EventPanel(id="events")


def _make_event(event_type: EventType, data: dict | None = None, **kwargs) -> AgentEvent:
    """Helper to create AgentEvent instances."""
    return AgentEvent(type=event_type, data=data or {}, **kwargs)


@pytest.mark.unit
class TestEventPanel:
    """EventPanel widget tests — isolated."""

    @pytest.mark.asyncio
    async def test_event_panel_mounts(self):
        """EventPanel renders and can be queried."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            assert panel is not None

    @pytest.mark.asyncio
    async def test_write_header(self):
        """write_header() adds content."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            panel.write_header()
            assert len(panel.lines) > 0

    @pytest.mark.asyncio
    async def test_handle_turn_start(self):
        """TURN_START event updates turn count."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            event = _make_event(EventType.TURN_START, {"iteration": 3})
            panel.handle_event(event)
            assert panel.turn_count == 3
            assert len(panel.lines) > 0

    @pytest.mark.asyncio
    async def test_handle_tool_call(self):
        """TOOL_CALL event renders tool name."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            event = _make_event(EventType.TOOL_CALL, {"name": "read_file"})
            panel.handle_event(event)
            assert len(panel.lines) > 0

    @pytest.mark.asyncio
    async def test_handle_tool_result_success(self):
        """TOOL_RESULT event renders success."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            event = _make_event(EventType.TOOL_RESULT, {"content": "file contents..."})
            panel.handle_event(event)
            assert len(panel.lines) > 0

    @pytest.mark.asyncio
    async def test_handle_tool_result_error(self):
        """TOOL_RESULT event with error renders failure."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            event = _make_event(EventType.TOOL_RESULT, {"error": "not found"})
            panel.handle_event(event)
            assert len(panel.lines) > 0

    @pytest.mark.asyncio
    async def test_handle_done(self):
        """DONE event renders completion."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            event = _make_event(EventType.DONE, {"total_iterations": 5})
            panel.handle_event(event)
            assert len(panel.lines) > 0

    @pytest.mark.asyncio
    async def test_handle_error(self):
        """ERROR event renders error text."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            event = _make_event(EventType.ERROR, {"error": "timeout"})
            panel.handle_event(event)
            assert len(panel.lines) > 0

    @pytest.mark.asyncio
    async def test_handle_billing(self):
        """BILLING event renders usage stats."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            event = _make_event(
                EventType.BILLING,
                {"total_tokens": 1500, "total_requests": 3},
            )
            panel.handle_event(event)
            assert len(panel.lines) > 0

    @pytest.mark.asyncio
    async def test_add_context_file(self):
        """add_context_file() tracks unique files."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            panel.add_context_file("src/auth.py")
            panel.add_context_file("src/auth.py")  # Duplicate
            panel.add_context_file("src/main.py")
            assert len(panel._context_files) == 2

    @pytest.mark.asyncio
    async def test_all_event_types_handled(self):
        """Every EventType is handled without exception."""
        async with EventPanelApp().run_test() as pilot:
            panel = pilot.app.query_one("#events", EventPanel)
            for event_type in EventType:
                event = _make_event(event_type, {"message": "test", "name": "test"})
                panel.handle_event(event)  # Should not raise
