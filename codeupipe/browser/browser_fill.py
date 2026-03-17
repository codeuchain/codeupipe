"""Fill an input element."""

from __future__ import annotations

from codeupipe import Payload
from .bridge import BrowserBridge


class BrowserFill:
    """Clear and fill an input by selector.

    Reads
    -----
    browser_selector : str — CSS selector or @ref
    browser_text     : str — text to fill

    Writes
    ------
    browser_output : str  — raw stdout
    browser_ok     : bool — success flag
    """

    def __init__(
        self,
        bridge: BrowserBridge,
        selector: str | None = None,
        text: str | None = None,
    ) -> None:
        self._bridge = bridge
        self._selector = selector
        self._text = text

    def call(self, payload: Payload) -> Payload:
        selector = self._selector or payload.get("browser_selector")
        text = self._text or payload.get("browser_text", "")
        if not selector:
            raise ValueError("BrowserFill requires 'browser_selector' in payload or selector in constructor")
        result = self._bridge.fill(selector, text)
        return (
            payload
            .insert("browser_output", result.output)
            .insert("browser_ok", result.ok)
        )
