"""Get page information (text, html, title, url, etc.)."""

from __future__ import annotations

from codeupipe import Payload
from .bridge import BrowserBridge


class BrowserGet:
    """Extract information from the page.

    Reads
    -----
    browser_get_what     : str — what to get (text, html, title, url, value, count, etc.)
    browser_get_selector : str | None — optional CSS selector to scope

    Writes
    ------
    browser_get_result : str  — extracted value
    browser_output     : str  — raw stdout
    browser_ok         : bool — success flag
    """

    def __init__(
        self,
        bridge: BrowserBridge,
        what: str | None = None,
        selector: str | None = None,
    ) -> None:
        self._bridge = bridge
        self._what = what
        self._selector = selector

    def call(self, payload: Payload) -> Payload:
        what = self._what or payload.get("browser_get_what")
        selector = self._selector or payload.get("browser_get_selector")
        if not what:
            raise ValueError("BrowserGet requires 'browser_get_what' in payload or what in constructor")
        result = self._bridge.get(what, selector)
        return (
            payload
            .insert("browser_get_result", result.stdout if result.ok else "")
            .insert("browser_output", result.output)
            .insert("browser_ok", result.ok)
        )
