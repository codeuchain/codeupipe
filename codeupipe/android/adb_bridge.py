"""
AdbBridge — subprocess wrapper around the ``adb`` CLI.

This is the single point of contact between codeupipe and the Android
Debug Bridge.  Every Android Filter delegates here.

The bridge is intentionally thin: build the command list, run it, return
stdout/stderr/returncode.  Filters interpret the output.

Architecture mirrors ``BrowserBridge`` from ``codeupipe.browser``.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import List, Optional

from .adb_result import AdbResult


__all__ = ["AdbBridge"]


class AdbBridge:
    """Subprocess bridge to ``adb``.

    Parameters
    ----------
    executable : str | None
        Path to the ``adb`` binary.  Resolved via ``shutil.which``
        when *None* (the default).
    serial : str | None
        Target device serial (``-s`` flag).  Use ``emulator-5554``
        for the default emulator, or a physical device serial.
    timeout : int
        Per-command timeout in seconds (default 30).
    """

    def __init__(
        self,
        executable: Optional[str] = None,
        serial: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self._executable = executable or shutil.which("adb") or "adb"
        self._serial = serial
        self._timeout = timeout

    # ── Core ─────────────────────────────────────────────────────────

    def run(self, *args: str, timeout: Optional[int] = None) -> AdbResult:
        """Execute an ``adb`` command and return the result."""
        cmd = self._build_command(list(args))
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self._timeout,
            )
            return AdbResult(
                stdout=proc.stdout.strip(),
                stderr=proc.stderr.strip(),
                returncode=proc.returncode,
                command=cmd,
            )
        except subprocess.TimeoutExpired:
            return AdbResult(
                stdout="",
                stderr="Timeout after {}s".format(timeout or self._timeout),
                returncode=-1,
                command=cmd,
            )
        except FileNotFoundError:
            return AdbResult(
                stdout="",
                stderr=(
                    "adb not found. "
                    "Install Android SDK platform-tools or set executable path."
                ),
                returncode=-2,
                command=cmd,
            )

    # ── Convenience methods (thin wrappers around run) ───────────────

    def devices(self) -> AdbResult:
        """List connected devices."""
        return self.run("devices")

    def shell(self, command: str) -> AdbResult:
        """Run a shell command on the device."""
        return self.run("shell", command)

    def tap(self, x: int, y: int) -> AdbResult:
        """Tap at screen coordinates."""
        return self.run("shell", "input", "tap", str(x), str(y))

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: int = 300,
    ) -> AdbResult:
        """Swipe from (x1, y1) to (x2, y2)."""
        return self.run(
            "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration),
        )

    def type_text(self, text: str) -> AdbResult:
        """Type text into the currently focused element.

        Spaces are replaced with ``%s`` for ADB ``input text``.
        """
        safe = text.replace(" ", "%s")
        return self.run("shell", "input", "text", safe)

    def install(self, apk_path: str, replace: bool = True) -> AdbResult:
        """Install an APK onto the device."""
        args = ["install"]
        if replace:
            args.append("-r")
        args.append(apk_path)
        return self.run(*args)

    def uninstall(self, package: str) -> AdbResult:
        """Uninstall a package."""
        return self.run("uninstall", package)

    def start_app(self, component: str) -> AdbResult:
        """Launch an app.  *component* is ``package/activity``."""
        return self.run("shell", "am", "start", "-n", component)

    def stop_app(self, package: str) -> AdbResult:
        """Force-stop an app."""
        return self.run("shell", "am", "force-stop", package)

    def screenshot(self, local_path: str) -> AdbResult:
        """Capture a screenshot and pull it to *local_path*.

        Uses ``screencap`` on device then ``adb pull``.
        """
        device_path = "/sdcard/cup_screenshot.png"
        cap = self.run("shell", "screencap", "-p", device_path)
        if not cap.ok:
            return cap
        return self.run("pull", device_path, local_path)

    def ui_dump(self) -> AdbResult:
        """Dump the UI hierarchy (XML).

        Uses ``uiautomator dump`` then reads the file.
        """
        device_path = "/sdcard/cup_uidump.xml"
        dump = self.run("shell", "uiautomator", "dump", device_path)
        if not dump.ok:
            return dump
        return self.shell("cat {}".format(device_path))

    def logcat(
        self,
        lines: int = 100,
        tag_filter: Optional[str] = None,
    ) -> AdbResult:
        """Capture recent logcat lines.

        Parameters
        ----------
        lines : int
            Number of recent lines to capture (``-t`` flag).
        tag_filter : str | None
            Tag filter spec (e.g. ``MyApp:V *:S``).
        """
        args = ["logcat", "-t", str(lines), "-d"]
        if tag_filter:
            args.append(tag_filter)
        return self.run(*args)

    def forward(self, local: str, remote: str) -> AdbResult:
        """Set up port forwarding."""
        return self.run("forward", local, remote)

    def push(self, local_path: str, device_path: str) -> AdbResult:
        """Push a file to the device."""
        return self.run("push", local_path, device_path)

    def pull(self, device_path: str, local_path: str) -> AdbResult:
        """Pull a file from the device."""
        return self.run("pull", device_path, local_path)

    # ── Internal ─────────────────────────────────────────────────────

    def _build_command(self, args: List[str]) -> List[str]:
        """Construct the full ``adb`` command line."""
        cmd = [self._executable]
        if self._serial:
            cmd.extend(["-s", self._serial])
        cmd.extend(args)
        return cmd
