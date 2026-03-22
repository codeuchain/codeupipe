"""
Bridge launcher — auto-start native compute services.

When the bridge probes and finds nothing listening, the launcher can
start the configured command (e.g. ``python spore_runner.py --port 8089``)
and wait for it to become healthy.

Also provides platform-specific service installation for persistent
background execution (launchd on macOS, systemd on Linux).

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .bridge_config import BridgeConfig

__all__ = [
    "BridgeLauncher",
    "LaunchResult",
    "install_service",
    "uninstall_service",
]


class LaunchResult:
    """Result of attempting to launch a bridge service."""

    def __init__(
        self,
        success: bool,
        pid: int = 0,
        message: str = "",
        config: Optional[BridgeConfig] = None,
    ):
        self.success = success
        self.pid = pid
        self.message = message
        self.config = config

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "pid": self.pid,
            "message": self.message,
        }


class BridgeLauncher:
    """Launch and manage native compute bridge processes.

    The launcher can:
    1. Start a bridge process from a configured command
    2. Wait for it to become healthy
    3. Stop it gracefully
    4. Install it as a system service (launchd/systemd)

    Parameters
    ----------
    config : BridgeConfig
        Configuration with ``auto_start`` command.
    wait_timeout : float
        How long to wait for the service to become healthy.
    poll_interval : float
        How often to check health during startup.
    """

    def __init__(
        self,
        config: BridgeConfig,
        wait_timeout: float = 30.0,
        poll_interval: float = 1.0,
    ):
        self.config = config
        self.wait_timeout = wait_timeout
        self.poll_interval = poll_interval
        self._process: Optional[subprocess.Popen] = None

    @property
    def is_running(self) -> bool:
        """Check if the managed process is still running."""
        if self._process is None:
            return False
        return self._process.poll() is None

    @property
    def pid(self) -> int:
        """PID of the managed process, or 0."""
        if self._process and self._process.poll() is None:
            return self._process.pid
        return 0

    def launch(self) -> LaunchResult:
        """Start the bridge service and wait for it to become healthy.

        Uses the ``auto_start`` field from BridgeConfig as the command.
        Falls back to ``python -m spore_runner`` if not configured.

        Returns a LaunchResult indicating success/failure.
        """
        cmd = self._build_command()
        if not cmd:
            return LaunchResult(
                success=False,
                message="No auto_start command configured",
                config=self.config,
            )

        try:
            # Start the process in the background
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # Detach from parent
            )

            # Wait for health
            if self._wait_for_health():
                return LaunchResult(
                    success=True,
                    pid=self._process.pid,
                    message=f"Bridge started on {self.config.base_url}",
                    config=self.config,
                )
            else:
                # Process started but never became healthy
                self.stop()
                return LaunchResult(
                    success=False,
                    message=f"Bridge started but health check failed "
                            f"after {self.wait_timeout}s",
                    config=self.config,
                )

        except FileNotFoundError as e:
            return LaunchResult(
                success=False,
                message=f"Command not found: {cmd[0]} ({e})",
                config=self.config,
            )
        except Exception as e:
            return LaunchResult(
                success=False,
                message=f"Failed to launch: {e}",
                config=self.config,
            )

    def stop(self) -> bool:
        """Stop the managed process gracefully."""
        if self._process is None:
            return False

        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
            return True
        except Exception:
            return False
        finally:
            self._process = None

    def _build_command(self) -> List[str]:
        """Build the launch command from config."""
        if self.config.auto_start:
            parts = self.config.auto_start.split()
            parts.extend(self.config.auto_start_args)
            return parts

        # No auto_start configured
        return []

    def _wait_for_health(self) -> bool:
        """Poll the health endpoint until it responds or timeout."""
        deadline = time.monotonic() + self.wait_timeout

        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)

            # Check if process died
            if self._process and self._process.poll() is not None:
                return False

            # Try health check
            try:
                req = urllib.request.Request(
                    self.config.health_url,
                    method="GET",
                    headers={"Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.getcode() == 200:
                        return True
            except Exception:
                continue

        return False


# ── Service Installation ─────────────────────────────────────────────

def install_service(
    config: BridgeConfig,
    service_name: str = "cup-bridge",
    description: str = "codeupipe compute bridge",
) -> Dict[str, Any]:
    """Install the bridge as a persistent background service.

    - macOS: Creates a LaunchAgent plist
    - Linux: Creates a systemd user unit
    - Windows: Creates a Task Scheduler task (basic)

    Returns a dict with {success, path, message}.
    """
    system = platform.system()

    if system == "Darwin":
        return _install_launchd(config, service_name, description)
    elif system == "Linux":
        return _install_systemd(config, service_name, description)
    else:
        return {
            "success": False,
            "message": f"Service installation not supported on {system}. "
                       f"Use auto_start in bridge config instead.",
        }


def uninstall_service(
    service_name: str = "cup-bridge",
) -> Dict[str, Any]:
    """Remove a previously installed bridge service."""
    system = platform.system()

    if system == "Darwin":
        return _uninstall_launchd(service_name)
    elif system == "Linux":
        return _uninstall_systemd(service_name)
    else:
        return {"success": False, "message": f"Not supported on {system}"}


# ── macOS LaunchAgent ────────────────────────────────────────────────

def _install_launchd(
    config: BridgeConfig,
    service_name: str,
    description: str,
) -> Dict[str, Any]:
    """Install a macOS LaunchAgent for the bridge."""
    label = f"com.codeupipe.{service_name}"
    cmd = config.auto_start.split() if config.auto_start else []
    cmd.extend(config.auto_start_args)

    if not cmd:
        return {"success": False, "message": "No auto_start command configured"}

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
"""
    for part in cmd:
        plist_content += f"        <string>{part}</string>\n"
    plist_content += f"""    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/{service_name}.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/{service_name}.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:{os.environ.get('PATH', '')}</string>
    </dict>
</dict>
</plist>
"""

    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / f"{label}.plist"
    plist_path.write_text(plist_content)

    # Load the agent
    try:
        subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass

    return {
        "success": True,
        "path": str(plist_path),
        "message": f"Installed LaunchAgent: {plist_path}",
        "load_command": f"launchctl load {plist_path}",
        "unload_command": f"launchctl unload {plist_path}",
    }


def _uninstall_launchd(service_name: str) -> Dict[str, Any]:
    """Remove a macOS LaunchAgent."""
    label = f"com.codeupipe.{service_name}"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"

    if not plist_path.exists():
        return {"success": False, "message": f"Not found: {plist_path}"}

    try:
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass

    plist_path.unlink()
    return {"success": True, "message": f"Removed: {plist_path}"}


# ── Linux systemd ───────────────────────────────────────────────────

def _install_systemd(
    config: BridgeConfig,
    service_name: str,
    description: str,
) -> Dict[str, Any]:
    """Install a systemd user unit for the bridge."""
    cmd = config.auto_start
    if config.auto_start_args:
        cmd += " " + " ".join(config.auto_start_args)

    if not cmd:
        return {"success": False, "message": "No auto_start command configured"}

    unit_content = f"""[Unit]
Description={description}
After=network.target

[Service]
Type=simple
ExecStart={cmd}
Restart=always
RestartSec=5
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
"""

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / f"{service_name}.service"
    unit_path.write_text(unit_content)

    # Reload and enable
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"],
                       capture_output=True, timeout=10)
        subprocess.run(["systemctl", "--user", "enable", service_name],
                       capture_output=True, timeout=10)
        subprocess.run(["systemctl", "--user", "start", service_name],
                       capture_output=True, timeout=10)
    except Exception:
        pass

    return {
        "success": True,
        "path": str(unit_path),
        "message": f"Installed systemd unit: {unit_path}",
        "start_command": f"systemctl --user start {service_name}",
        "stop_command": f"systemctl --user stop {service_name}",
    }


def _uninstall_systemd(service_name: str) -> Dict[str, Any]:
    """Remove a systemd user unit."""
    unit_path = (
        Path.home() / ".config" / "systemd" / "user" / f"{service_name}.service"
    )

    if not unit_path.exists():
        return {"success": False, "message": f"Not found: {unit_path}"}

    try:
        subprocess.run(["systemctl", "--user", "stop", service_name],
                       capture_output=True, timeout=10)
        subprocess.run(["systemctl", "--user", "disable", service_name],
                       capture_output=True, timeout=10)
    except Exception:
        pass

    unit_path.unlink()

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"],
                       capture_output=True, timeout=10)
    except Exception:
        pass

    return {"success": True, "message": f"Removed: {unit_path}"}
