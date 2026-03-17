"""Take a screenshot."""

from __future__ import annotations

from codeupipe import Payload
from .bridge import BrowserBridge


class BrowserScreenshot:
    """Capture a screenshot of the current page.

    Reads
    -----
    browser_screenshot_path : str — file path to save (optional)

    Writes
    ------
    browser_screenshot : str  — path where screenshot was saved
    browser_output     : str  — raw stdout
    browser_ok         : bool — success flag
    """

    def __init__(self, bridge: BrowserBridge, path: str | None = None) -> None:
        self._bridge = bridge
        self._path = path

    def call(self, payload: Payload) -> Payload:
        path = self._path or payload.get("browser_screenshot_path")
        result = self._bridge.screenshot(path)
        return (
            payload
            .insert("browser_screenshot", path or "")
            .insert("browser_output", result.output)
            .insert("browser_ok", result.ok)
        )
