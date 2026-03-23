"""Tap at screen coordinates."""

from __future__ import annotations

from typing import Optional

from codeupipe import Payload
from .adb_bridge import AdbBridge


class AndroidTap:
    """Tap at (x, y) screen coordinates.

    Reads
    -----
    android_x : int — X coordinate
    android_y : int — Y coordinate

    Writes
    ------
    android_output : str  — raw output
    android_ok     : bool — success flag
    """

    def __init__(
        self,
        bridge: AdbBridge,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> None:
        self._bridge = bridge
        self._x = x
        self._y = y

    def call(self, payload: Payload) -> Payload:
        x = self._x if self._x is not None else payload.get("android_x")
        y = self._y if self._y is not None else payload.get("android_y")
        if x is None or y is None:
            raise ValueError(
                "AndroidTap requires 'android_x' and 'android_y' in payload "
                "or x/y in constructor"
            )
        result = self._bridge.tap(x, y)
        return (
            payload
            .insert("android_output", result.output)
            .insert("android_ok", result.ok)
        )
