"""Type text into the focused element."""

from __future__ import annotations

from typing import Optional

from codeupipe import Payload
from .adb_bridge import AdbBridge


class AndroidType:
    """Type text into the currently focused input.

    Reads
    -----
    android_text : str — text to type

    Writes
    ------
    android_output : str  — raw output
    android_ok     : bool — success flag
    """

    def __init__(self, bridge: AdbBridge, text: Optional[str] = None) -> None:
        self._bridge = bridge
        self._text = text

    def call(self, payload: Payload) -> Payload:
        text = self._text or payload.get("android_text")
        if not text:
            raise ValueError(
                "AndroidType requires 'android_text' in payload "
                "or text in constructor"
            )
        result = self._bridge.type_text(text)
        return (
            payload
            .insert("android_output", result.output)
            .insert("android_ok", result.ok)
        )
