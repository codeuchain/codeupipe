"""Stop an app by package name."""

from __future__ import annotations

from typing import Optional

from codeupipe import Payload
from .adb_bridge import AdbBridge


class AndroidClose:
    """Force-stop an Android app.

    Reads
    -----
    android_package : str — package name to stop

    Writes
    ------
    android_output : str  — raw output
    android_ok     : bool — success flag
    """

    def __init__(self, bridge: AdbBridge, package: Optional[str] = None) -> None:
        self._bridge = bridge
        self._package = package

    def call(self, payload: Payload) -> Payload:
        package = self._package or payload.get("android_package")
        if not package:
            raise ValueError(
                "AndroidClose requires 'android_package' in payload "
                "or package in constructor"
            )
        result = self._bridge.stop_app(package)
        return (
            payload
            .insert("android_output", result.output)
            .insert("android_ok", result.ok)
        )
