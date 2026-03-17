"""ChatPane — scrollable conversation display.

Renders the conversation as a stream of user and agent messages.
Agent responses are rendered as markdown with syntax highlighting.
Supports streaming — partial content appends to the current message
as tokens arrive.

This widget consumes AgentEvent.RESPONSE events and renders them
into a scrollable RichLog.
"""

from __future__ import annotations

from rich.markdown import Markdown
from rich.text import Text
from textual.widgets import RichLog


class ChatPane(RichLog):
    """Scrollable chat pane showing user/agent conversation.

    Messages are appended via write_user() and write_agent().
    Agent messages support streaming: call begin_agent() to start,
    stream_token() for each token, and end_agent() to finalize.
    """

    DEFAULT_CSS = """
    ChatPane {
        width: 1fr;
        min-width: 40;
        border-right: tall $accent;
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
        self._streaming = False
        self._stream_buffer: list[str] = []

    def write_user(self, message: str) -> None:
        """Append a user message to the chat.

        Args:
            message: The user's input text.
        """
        label = Text("You: ", style="bold cyan")
        label.append(message)
        self.write(label)
        self.write(Text(""))  # Spacer

    def write_agent(self, message: str) -> None:
        """Append a complete agent message (rendered as markdown).

        Use this for non-streaming responses. For streaming,
        use begin_agent/stream_token/end_agent instead.

        Args:
            message: The agent's full response.
        """
        label = Text("Agent: ", style="bold green")
        self.write(label)
        self.write(Markdown(message))
        self.write(Text(""))  # Spacer

    def begin_agent(self) -> None:
        """Start a new streaming agent response."""
        self._streaming = True
        self._stream_buffer.clear()
        label = Text("Agent: ", style="bold green")
        self.write(label)

    def stream_token(self, token: str) -> None:
        """Append a single token to the current streaming response.

        Args:
            token: A text token from the agent's response.
        """
        if not self._streaming:
            self.begin_agent()
        self._stream_buffer.append(token)
        # Re-render the accumulated markdown so far
        accumulated = "".join(self._stream_buffer)
        # Remove the last line (partial render) and replace
        if len(self._stream_buffer) > 1:
            self.clear()
            # We need to re-render previous content, but for MVP
            # just show the accumulated text as a Text object (fast)
            self.write(Text(accumulated, style=""))

    def end_agent(self) -> None:
        """Finalize the current streaming agent response.

        Renders the accumulated buffer as full markdown.
        """
        if self._stream_buffer:
            accumulated = "".join(self._stream_buffer)
            # Re-render as proper markdown now that stream is complete
            self.write(Markdown(accumulated))
            self.write(Text(""))  # Spacer
        self._streaming = False
        self._stream_buffer.clear()

    def write_error(self, message: str) -> None:
        """Append an error message.

        Args:
            message: The error text.
        """
        error_text = Text(f"❌ Error: {message}", style="bold red")
        self.write(error_text)
        self.write(Text(""))  # Spacer

    def write_system(self, message: str) -> None:
        """Append a system/info message.

        Args:
            message: The system message text.
        """
        sys_text = Text(f"ℹ️  {message}", style="dim")
        self.write(sys_text)
