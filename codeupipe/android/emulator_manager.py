"""
EmulatorManager — AVD lifecycle management.

Creates, starts, stops, and lists Android Virtual Devices.  Uses the
``avdmanager`` and ``emulator`` CLIs from the Android SDK.

When ``start()`` is called it spawns an emulator in the background and
returns an ``AdbBridge`` wired to that emulator's serial.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from .adb_bridge import AdbBridge
from .adb_result import AdbResult


__all__ = ["EmulatorManager"]


class EmulatorManager:
    """Manage Android Virtual Devices (AVDs).

    Parameters
    ----------
    avdmanager : str | None
        Path to ``avdmanager``.  Resolved via ``shutil.which``.
    emulator : str | None
        Path to ``emulator``.  Resolved via ``shutil.which``.
    adb_executable : str | None
        Path to ``adb`` — forwarded to any ``AdbBridge`` created by ``start()``.
    timeout : int
        Default per-command timeout in seconds.
    """

    def __init__(
        self,
        avdmanager: Optional[str] = None,
        emulator: Optional[str] = None,
        adb_executable: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        self._avdmanager = avdmanager or shutil.which("avdmanager") or "avdmanager"
        self._emulator = emulator or shutil.which("emulator") or "emulator"
        self._adb_executable = adb_executable
        self._timeout = timeout

    # ── AVD CRUD ─────────────────────────────────────────────────────

    def create_avd(
        self,
        name: str,
        package: str = "system-images;android-34;google_apis;arm64-v8a",
        device: str = "pixel_6",
        force: bool = True,
    ) -> AdbResult:
        """Create a new AVD.

        Parameters
        ----------
        name : str
            AVD name (used by ``emulator -avd <name>``).
        package : str
            System image package string.
        device : str
            Hardware profile (default ``pixel_6``).
        force : bool
            Overwrite if AVD already exists.
        """
        cmd = [
            self._avdmanager, "create", "avd",
            "-n", name,
            "-k", package,
            "-d", device,
        ]
        if force:
            cmd.append("--force")
        return self._run(cmd)

    def list_avds(self) -> AdbResult:
        """List available AVDs."""
        return self._run([self._avdmanager, "list", "avd", "-c"])

    def delete_avd(self, name: str) -> AdbResult:
        """Delete an AVD by name."""
        return self._run([self._avdmanager, "delete", "avd", "-n", name])

    # ── Emulator lifecycle ───────────────────────────────────────────

    def start(
        self,
        avd_name: str,
        headless: bool = True,
        port: int = 5554,
    ) -> AdbBridge:
        """Launch an emulator for *avd_name* and return a wired ``AdbBridge``.

        The emulator is spawned as a background process.  Use ``stop()``
        or ``AdbBridge.run("emu", "kill")`` to tear it down.

        Parameters
        ----------
        avd_name : str
            AVD name to boot.
        headless : bool
            Run without a GUI window (``-no-window``).
        port : int
            Console port — the device serial will be ``emulator-{port}``.
        """
        cmd = [self._emulator, "-avd", avd_name, "-port", str(port)]
        if headless:
            cmd.extend(["-no-window", "-no-audio", "-no-boot-anim"])
        # Fire and forget — emulator runs in background
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        serial = "emulator-{}".format(port)
        return AdbBridge(
            executable=self._adb_executable,
            serial=serial,
        )

    def stop(self, serial: str = "emulator-5554") -> AdbResult:
        """Kill a running emulator by serial."""
        bridge = AdbBridge(executable=self._adb_executable, serial=serial)
        return bridge.run("emu", "kill")

    def wait_for_boot(
        self,
        serial: str = "emulator-5554",
        timeout: int = 120,
    ) -> AdbResult:
        """Block until the emulator reports ``sys.boot_completed=1``.

        Parameters
        ----------
        serial : str
            Emulator serial.
        timeout : int
            Maximum seconds to wait.
        """
        bridge = AdbBridge(executable=self._adb_executable, serial=serial)
        return bridge.run(
            "shell", "getprop", "sys.boot_completed",
            timeout=timeout,
        )

    # ── Internal ─────────────────────────────────────────────────────

    def _run(self, cmd, timeout=None):
        """Run a subprocess and return AdbResult."""
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
                stderr="Command not found: {}".format(cmd[0]),
                returncode=-2,
                command=cmd,
            )
