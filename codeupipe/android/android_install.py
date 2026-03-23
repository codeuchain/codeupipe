"""Install an APK onto the device."""

from __future__ import annotations

from typing import Optional

from codeupipe import Payload
from .adb_bridge import AdbBridge


class AndroidInstall:
    """Install an APK via ``adb install``.

    Reads
    -----
    android_apk : str — path to the APK file

    Writes
    ------
    android_output : str  — raw output
    android_ok     : bool — success flag
    """

    def __init__(self, bridge: AdbBridge, apk: Optional[str] = None) -> None:
        self._bridge = bridge
        self._apk = apk

    def call(self, payload: Payload) -> Payload:
        apk = self._apk or payload.get("android_apk")
        if not apk:
            raise ValueError(
                "AndroidInstall requires 'android_apk' in payload "
                "or apk in constructor"
            )
        result = self._bridge.install(apk)
        return (
            payload
            .insert("android_output", result.output)
            .insert("android_ok", result.ok)
        )
