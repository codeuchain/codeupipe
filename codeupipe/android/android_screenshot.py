"""Capture a screenshot."""

from __future__ import annotations

from typing import Optional

from codeupipe import Payload
from .adb_bridge import AdbBridge


class AndroidScreenshot:
    """Capture a screenshot from the device.

    Reads
    -----
    android_screenshot_path : str — local file path to save (optional)

    Writes
    ------
    android_screenshot : str  — path where screenshot was saved
    android_output     : str  — raw output
    android_ok         : bool — success flag
    """

    _DEFAULT_PATH = "/tmp/cup_android_screenshot.png"

    def __init__(self, bridge: AdbBridge, path: Optional[str] = None) -> None:
        self._bridge = bridge
        self._path = path

    def call(self, payload: Payload) -> Payload:
        path = (
            self._path
            or payload.get("android_screenshot_path")
            or self._DEFAULT_PATH
        )
        result = self._bridge.screenshot(path)
        return (
            payload
            .insert("android_screenshot", path)
            .insert("android_output", result.output)
            .insert("android_ok", result.ok)
        )
