"""Raw adb shell escape hatch."""

from __future__ import annotations

from typing import Optional

from codeupipe import Payload
from .adb_bridge import AdbBridge


class AndroidShell:
    """Execute an arbitrary ``adb shell`` command — the escape hatch.

    This is the Android equivalent of ``BrowserRaw``.  Any shell command
    is reachable.

    Reads
    -----
    android_shell_cmd : str — shell command to run

    Writes
    ------
    android_shell  : str  — command stdout (empty on failure)
    android_output : str  — raw output
    android_ok     : bool — success flag
    """

    def __init__(self, bridge: AdbBridge, command: Optional[str] = None) -> None:
        self._bridge = bridge
        self._command = command

    def call(self, payload: Payload) -> Payload:
        command = self._command or payload.get("android_shell_cmd")
        if not command:
            raise ValueError(
                "AndroidShell requires 'android_shell_cmd' in payload "
                "or command in constructor"
            )
        result = self._bridge.shell(command)
        return (
            payload
            .insert("android_shell", result.stdout if result.ok else "")
            .insert("android_output", result.output)
            .insert("android_ok", result.ok)
        )
