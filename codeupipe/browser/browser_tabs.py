"""List browser tabs."""

from __future__ import annotations

from codeupipe import Payload
from .bridge import BrowserBridge


class BrowserTabs:
    """List all open browser tabs.

    Writes
    ------
    browser_tabs   : str  — tab list output
    browser_output : str  — raw stdout
    browser_ok     : bool — success flag
    """

    def __init__(self, bridge: BrowserBridge) -> None:
        self._bridge = bridge

    def call(self, payload: Payload) -> Payload:
        result = self._bridge.tabs()
        return (
            payload
            .insert("browser_tabs", result.stdout if result.ok else "")
            .insert("browser_output", result.output)
            .insert("browser_ok", result.ok)
        )
