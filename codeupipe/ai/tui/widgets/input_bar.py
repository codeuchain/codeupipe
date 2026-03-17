"""InputBar — user input with ghost-text autocomplete and mode indicator.

The input bar sits at the bottom of the chat screen. It supports:
- Ghost text autocompletion for / commands (SuggestFromList)
- Mode indicator prefix ([agent] or [ask])
- Input history navigation (up/down arrows)
- Multi-line input (Alt+Enter for newline, Enter to submit)
"""

from __future__ import annotations

from textual import on
from textual.message import Message
from textual.suggester import SuggestFromList
from textual.widgets import Input


SLASH_COMMANDS = [
    "/help",
    "/clear",
    "/save",
    "/sessions",
    "/model",
    "/exit",
]


class InputBar(Input):
    """Agent input bar with ghost-text slash command completion.

    Emits InputBar.Submitted when the user presses Enter.
    Supports input history via up/down arrow navigation.
    """

    DEFAULT_CSS = """
    InputBar {
        dock: bottom;
        margin: 0 1;
        height: 3;
    }
    """

    class Submitted(Message):
        """Fired when user submits input."""

        def __init__(self, value: str, mode: str) -> None:
            super().__init__()
            self.value = value
            self.mode = mode

    def __init__(self, **kwargs) -> None:
        super().__init__(
            placeholder="Type a message... (/ for commands, @ for files, ! for shell)",
            suggester=SuggestFromList(SLASH_COMMANDS, case_sensitive=False),
            **kwargs,
        )
        self._history: list[str] = []
        self._history_index: int = -1
        self._mode: str = "agent"

    @property
    def mode(self) -> str:
        """Current interaction mode (agent or ask)."""
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._mode = value

    def cycle_mode(self) -> str:
        """Cycle between agent and ask modes. Returns the new mode."""
        self._mode = "ask" if self._mode == "agent" else "agent"
        return self._mode

    @on(Input.Submitted)
    def on_submit(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        event.stop()
        value = event.value.strip()
        if not value:
            return
        # Store in history
        self._history.append(value)
        self._history_index = -1
        # Clear the input
        self.value = ""
        # Post our own message with mode info
        self.post_message(InputBar.Submitted(value, self._mode))

    def history_back(self) -> None:
        """Navigate to previous item in history."""
        if not self._history:
            return
        if self._history_index == -1:
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        self.value = self._history[self._history_index]

    def history_forward(self) -> None:
        """Navigate to next item in history."""
        if self._history_index == -1:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.value = self._history[self._history_index]
        else:
            self._history_index = -1
            self.value = ""
