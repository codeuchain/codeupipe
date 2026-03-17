"""EventPanel — real-time agent activity sidebar.

Shows tool calls, turn progress, context files, and usage stats.
Each AgentEvent is rendered as a compact one-line summary.
Verbose events (tool calls, tool results) show when verbose mode
is enabled.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import RichLog

from codeupipe.ai.agent.events import AgentEvent, EventType


class EventPanel(RichLog):
    """Activity sidebar showing agent events and tool calls.

    Renders AgentEvent objects as compact text entries.
    Updates in real-time as the agent processes.
    """

    DEFAULT_CSS = """
    EventPanel {
        width: 35;
        min-width: 25;
        max-width: 50;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            wrap=True,
            markup=True,
            highlight=True,
            auto_scroll=True,
            **kwargs,
        )
        self._turn_count = 0
        self._context_files: list[str] = []

    def handle_event(self, event: AgentEvent) -> None:
        """Process an AgentEvent and render it in the panel.

        Args:
            event: The agent event to display.
        """
        match event.type:
            case EventType.TURN_START:
                self._turn_count = event.data.get("iteration", self._turn_count + 1)
                header = Text(f"[Turn {self._turn_count}]", style="bold yellow")
                self.write(header)

            case EventType.TOOL_CALL:
                tool_name = event.data.get("name", "unknown")
                tool_text = Text(f"  🔧 {tool_name}", style="cyan")
                self.write(tool_text)

            case EventType.TOOL_RESULT:
                status = "✓" if not event.data.get("error") else "✗"
                style = "green" if status == "✓" else "red"
                result_text = Text(f"    {status}", style=style)
                # Add brief result summary if available
                content = event.data.get("content", "")
                if content and isinstance(content, str):
                    summary = content[:50] + "..." if len(content) > 50 else content
                    result_text.append(f" {summary}", style="dim")
                self.write(result_text)

            case EventType.TURN_END:
                duration = event.data.get("duration", 0)
                if duration:
                    done_text = Text(f"  ✓ {duration:.1f}s", style="green dim")
                else:
                    done_text = Text("  ✓", style="green dim")
                self.write(done_text)

            case EventType.ERROR:
                error_msg = str(event.data.get("error", event.data))
                error_text = Text(f"  ❌ {error_msg[:60]}", style="bold red")
                self.write(error_text)

            case EventType.BILLING:
                tokens = event.data.get("total_tokens", 0)
                requests = event.data.get("total_requests", 0)
                billing_text = Text(
                    f"  📊 {requests} req │ {tokens} tokens",
                    style="dim",
                )
                self.write(billing_text)

            case EventType.NOTIFICATION:
                message = event.data.get("message", "")
                notif_text = Text(f"  📢 {message[:60]}", style="yellow")
                self.write(notif_text)

            case EventType.DONE:
                total = event.data.get("total_iterations", 0)
                done_text = Text(f"✅ Complete ({total} turns)", style="bold green")
                self.write(done_text)
                self.write(Text(""))  # Spacer

            case _:
                # STATE_CHANGE or unknown — show raw
                self.write(Text(f"  ⚡ {event.type}: {str(event.data)[:40]}", style="dim"))

    def add_context_file(self, path: str) -> None:
        """Track a context file used by the agent.

        Args:
            path: File path added to context.
        """
        if path not in self._context_files:
            self._context_files.append(path)

    def write_header(self) -> None:
        """Write the initial panel header."""
        self.write(Text("Activity", style="bold underline"))
        self.write(Text("─────────", style="dim"))

    @property
    def turn_count(self) -> int:
        """Current turn count."""
        return self._turn_count
