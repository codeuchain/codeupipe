"""Close the browser."""

from __future__ import annotations

from codeupipe import Payload
from .bridge import BrowserBridge


class BrowserClose:
    """Close the browser session.

    Writes
    ------
    browser_output : str  — raw stdout
    browser_ok     : bool — success flag
    """

    def __init__(self, bridge: BrowserBridge) -> None:
        self._bridge = bridge

    def call(self, payload: Payload) -> Payload:
        result = self._bridge.close()
        return (
            payload
            .insert("browser_output", result.output)
            .insert("browser_ok", result.ok)
        )
