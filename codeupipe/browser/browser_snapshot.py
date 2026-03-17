"""Get accessibility snapshot of the page."""

from __future__ import annotations

from codeupipe import Payload
from .bridge import BrowserBridge


class BrowserSnapshot:
    """Capture an accessibility tree snapshot.

    Reads
    -----
    browser_interactive : bool — only interactive elements (default True)

    Writes
    ------
    browser_snapshot : str  — accessibility tree text with @refs
    browser_output  : str  — raw stdout
    browser_ok      : bool — success flag
    """

    def __init__(self, bridge: BrowserBridge, interactive: bool = True) -> None:
        self._bridge = bridge
        self._interactive = interactive

    def call(self, payload: Payload) -> Payload:
        interactive = payload.get("browser_interactive", self._interactive)
        result = self._bridge.snapshot(interactive=interactive)
        return (
            payload
            .insert("browser_snapshot", result.stdout if result.ok else "")
            .insert("browser_output", result.output)
            .insert("browser_ok", result.ok)
        )
