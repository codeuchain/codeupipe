"""Execute an adb shell command."""

from __future__ import annotations

from typing import Optional

from codeupipe import Payload
from .adb_bridge import AdbBridge


class AndroidEval:
    """Run an arbitrary ``adb shell`` command.

    Reads
    -----
    android_command : str — shell command to execute

    Writes
    ------
    android_eval   : str  — command output (empty on failure)
    android_output : str  — raw output
    android_ok     : bool — success flag
    """

    def __init__(self, bridge: AdbBridge, command: Optional[str] = None) -> None:
        self._bridge = bridge
        self._command = command

    def call(self, payload: Payload) -> Payload:
        command = self._command or payload.get("android_command")
        if not command:
            raise ValueError(
                "AndroidEval requires 'android_command' in payload "
                "or command in constructor"
            )
        result = self._bridge.shell(command)
        return (
            payload
            .insert("android_eval", result.stdout if result.ok else "")
            .insert("android_output", result.output)
            .insert("android_ok", result.ok)
        )
