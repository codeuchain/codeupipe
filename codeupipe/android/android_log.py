"""Capture logcat output."""

from __future__ import annotations

from typing import Optional

from codeupipe import Payload
from .adb_bridge import AdbBridge


class AndroidLog:
    """Capture recent logcat entries.

    Reads
    -----
    android_log_filter : str | None — tag filter spec (e.g. ``MyApp:V``)

    Writes
    ------
    android_log    : str  — logcat text
    android_output : str  — raw output
    android_ok     : bool — success flag
    """

    def __init__(
        self,
        bridge: AdbBridge,
        lines: int = 100,
        tag_filter: Optional[str] = None,
    ) -> None:
        self._bridge = bridge
        self._lines = lines
        self._tag_filter = tag_filter

    def call(self, payload: Payload) -> Payload:
        tag_filter = self._tag_filter or payload.get("android_log_filter")
        result = self._bridge.logcat(lines=self._lines, tag_filter=tag_filter)
        return (
            payload
            .insert("android_log", result.stdout if result.ok else "")
            .insert("android_output", result.output)
            .insert("android_ok", result.ok)
        )
