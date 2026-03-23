"""Dump the UI hierarchy (XML)."""

from __future__ import annotations

from codeupipe import Payload
from .adb_bridge import AdbBridge


class AndroidSnapshot:
    """Capture the UI hierarchy as XML via ``uiautomator dump``.

    Writes
    ------
    android_snapshot : str  — UI hierarchy XML (empty on failure)
    android_output   : str  — raw output
    android_ok       : bool — success flag
    """

    def __init__(self, bridge: AdbBridge) -> None:
        self._bridge = bridge

    def call(self, payload: Payload) -> Payload:
        result = self._bridge.ui_dump()
        return (
            payload
            .insert("android_snapshot", result.stdout if result.ok else "")
            .insert("android_output", result.output)
            .insert("android_ok", result.ok)
        )
