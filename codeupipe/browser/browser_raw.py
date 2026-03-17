"""Send a raw CDP command."""

from __future__ import annotations

from typing import Any, Dict, Optional

from codeupipe import Payload
from .bridge import BrowserBridge


class BrowserRaw:
    """Execute an arbitrary Chrome DevTools Protocol command.

    This is the escape hatch — any CDP domain/method is reachable.

    Reads
    -----
    browser_cdp_method : str            — CDP method (e.g. ``Page.navigate``)
    browser_cdp_params : dict | None    — CDP params

    Writes
    ------
    browser_raw    : str  — CDP response (JSON string)
    browser_output : str  — raw stdout
    browser_ok     : bool — success flag
    """

    def __init__(
        self,
        bridge: BrowserBridge,
        method: str | None = None,
        params: Dict[str, Any] | None = None,
    ) -> None:
        self._bridge = bridge
        self._method = method
        self._params = params

    def call(self, payload: Payload) -> Payload:
        method = self._method or payload.get("browser_cdp_method")
        params = self._params or payload.get("browser_cdp_params")
        if not method:
            raise ValueError("BrowserRaw requires 'browser_cdp_method' in payload or method in constructor")
        result = self._bridge.raw(method, params)
        return (
            payload
            .insert("browser_raw", result.stdout if result.ok else "")
            .insert("browser_output", result.output)
            .insert("browser_ok", result.ok)
        )
