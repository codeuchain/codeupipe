"""Navigate to a URL."""

from __future__ import annotations

from codeupipe import Payload
from .bridge import BrowserBridge


class BrowserOpen:
    """Open a URL in the browser.

    Reads
    -----
    browser_url : str  — URL to navigate to (or ``url`` constructor arg)

    Writes
    ------
    browser_url    : str  — confirmed URL after navigation
    browser_output : str  — raw stdout
    browser_ok     : bool — success flag
    """

    def __init__(self, bridge: BrowserBridge, url: str | None = None) -> None:
        self._bridge = bridge
        self._url = url

    def call(self, payload: Payload) -> Payload:
        url = self._url or payload.get("browser_url")
        if not url:
            raise ValueError("BrowserOpen requires 'browser_url' in payload or url in constructor")
        result = self._bridge.open(url)
        return (
            payload
            .insert("browser_url", url)
            .insert("browser_output", result.output)
            .insert("browser_ok", result.ok)
        )
