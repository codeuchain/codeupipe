"""Click an element."""

from __future__ import annotations

from codeupipe import Payload
from .bridge import BrowserBridge


class BrowserClick:
    """Click an element by CSS selector or @ref.

    Reads
    -----
    browser_selector : str — CSS selector or @ref (e.g. ``@e1``)

    Writes
    ------
    browser_output : str  — raw stdout
    browser_ok     : bool — success flag
    """

    def __init__(self, bridge: BrowserBridge, selector: str | None = None) -> None:
        self._bridge = bridge
        self._selector = selector

    def call(self, payload: Payload) -> Payload:
        selector = self._selector or payload.get("browser_selector")
        if not selector:
            raise ValueError("BrowserClick requires 'browser_selector' in payload or selector in constructor")
        result = self._bridge.click(selector)
        return (
            payload
            .insert("browser_output", result.output)
            .insert("browser_ok", result.ok)
        )
