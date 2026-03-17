"""Evaluate JavaScript in the page."""

from __future__ import annotations

from codeupipe import Payload
from .bridge import BrowserBridge


class BrowserEval:
    """Run a JavaScript expression in the active page.

    Reads
    -----
    browser_expression : str — JS expression to evaluate

    Writes
    ------
    browser_eval   : str  — evaluation result
    browser_output : str  — raw stdout
    browser_ok     : bool — success flag
    """

    def __init__(self, bridge: BrowserBridge, expression: str | None = None) -> None:
        self._bridge = bridge
        self._expression = expression

    def call(self, payload: Payload) -> Payload:
        expression = self._expression or payload.get("browser_expression")
        if not expression:
            raise ValueError("BrowserEval requires 'browser_expression' in payload or expression in constructor")
        result = self._bridge.evaluate(expression)
        return (
            payload
            .insert("browser_eval", result.stdout if result.ok else "")
            .insert("browser_output", result.output)
            .insert("browser_ok", result.ok)
        )
