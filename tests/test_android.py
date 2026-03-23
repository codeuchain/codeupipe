"""
Tests for codeupipe.android — ADB bridge, emulator manager, and Android filters.

Mirrors the structure of the browser module tests.  All ADB/emulator
subprocess calls are mocked so no real device or SDK is required.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from codeupipe import Payload

# ── Imports under test ──────────────────────────────────────────────

from codeupipe.android import (
    AdbBridge,
    AdbResult,
    AndroidClose,
    AndroidEval,
    AndroidInstall,
    AndroidLog,
    AndroidOpen,
    AndroidScreenshot,
    AndroidShell,
    AndroidSnapshot,
    AndroidTap,
    AndroidType,
    EmulatorManager,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _ok_proc(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode=0, stdout=stdout, stderr=stderr)


def _fail_proc(stderr: str = "error") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr=stderr)


def _make_bridge(**kwargs) -> AdbBridge:
    """Create an AdbBridge with defaults suitable for testing."""
    return AdbBridge(**kwargs)


# ════════════════════════════════════════════════════════════════════
# AdbResult
# ════════════════════════════════════════════════════════════════════

class TestAdbResult:
    """AdbResult data class — mirrors BrowserResult."""

    def test_ok_when_returncode_zero(self):
        r = AdbResult(stdout="fine", stderr="", returncode=0, command=["adb", "devices"])
        assert r.ok is True

    def test_not_ok_when_returncode_nonzero(self):
        r = AdbResult(stdout="", stderr="fail", returncode=1, command=["adb", "shell"])
        assert r.ok is False

    def test_output_returns_stdout_on_success(self):
        r = AdbResult(stdout="hello", stderr="", returncode=0)
        assert r.output == "hello"

    def test_output_returns_stderr_on_failure(self):
        r = AdbResult(stdout="", stderr="bad", returncode=1)
        assert r.output == "bad"

    def test_frozen(self):
        r = AdbResult(stdout="x", stderr="", returncode=0)
        with pytest.raises(AttributeError):
            r.stdout = "y"  # type: ignore[misc]

    def test_default_command_is_empty_list(self):
        r = AdbResult(stdout="", stderr="", returncode=0)
        assert r.command == []


# ════════════════════════════════════════════════════════════════════
# AdbBridge
# ════════════════════════════════════════════════════════════════════

class TestAdbBridge:
    """Subprocess wrapper around ``adb``."""

    @patch("subprocess.run", return_value=_ok_proc("device123\tdevice"))
    def test_devices(self, mock_run):
        bridge = _make_bridge()
        result = bridge.devices()
        assert result.ok
        assert "device123" in result.stdout

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_shell(self, mock_run):
        bridge = _make_bridge()
        result = bridge.shell("ls /sdcard")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "shell" in cmd
        assert "ls /sdcard" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_tap(self, mock_run):
        bridge = _make_bridge()
        result = bridge.tap(100, 200)
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "input" in cmd
        assert "tap" in cmd
        assert "100" in cmd
        assert "200" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_swipe(self, mock_run):
        bridge = _make_bridge()
        result = bridge.swipe(100, 200, 300, 400, duration=500)
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "swipe" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_type_text(self, mock_run):
        bridge = _make_bridge()
        result = bridge.type_text("hello world")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "input" in cmd
        assert "text" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_install(self, mock_run):
        bridge = _make_bridge()
        result = bridge.install("/tmp/app.apk")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "install" in cmd
        assert "/tmp/app.apk" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_uninstall(self, mock_run):
        bridge = _make_bridge()
        result = bridge.uninstall("com.example.app")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "uninstall" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_start_app(self, mock_run):
        bridge = _make_bridge()
        result = bridge.start_app("com.example.app/.MainActivity")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "am" in cmd
        assert "start" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_stop_app(self, mock_run):
        bridge = _make_bridge()
        result = bridge.stop_app("com.example.app")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "am" in cmd
        assert "force-stop" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_screenshot(self, mock_run):
        bridge = _make_bridge()
        result = bridge.screenshot("/tmp/screen.png")
        assert result.ok

    @patch("subprocess.run", return_value=_ok_proc("<hierarchy></hierarchy>"))
    def test_ui_dump(self, mock_run):
        bridge = _make_bridge()
        result = bridge.ui_dump()
        assert result.ok

    @patch("subprocess.run", return_value=_ok_proc("logline1\nlogline2"))
    def test_logcat(self, mock_run):
        bridge = _make_bridge()
        result = bridge.logcat(lines=10)
        assert result.ok
        assert "logline1" in result.stdout

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_forward(self, mock_run):
        bridge = _make_bridge()
        result = bridge.forward("tcp:8080", "tcp:8080")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "forward" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_push(self, mock_run):
        bridge = _make_bridge()
        result = bridge.push("/local/file.txt", "/sdcard/file.txt")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "push" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_pull(self, mock_run):
        bridge = _make_bridge()
        result = bridge.pull("/sdcard/file.txt", "/local/file.txt")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "pull" in cmd

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=30))
    def test_timeout_returns_error_result(self, mock_run):
        bridge = _make_bridge(timeout=30)
        result = bridge.run("devices")
        assert not result.ok
        assert "Timeout" in result.stderr

    @patch("subprocess.run", side_effect=FileNotFoundError())
    def test_adb_not_found(self, mock_run):
        bridge = _make_bridge()
        result = bridge.run("devices")
        assert not result.ok
        assert "adb not found" in result.stderr.lower()

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_serial_passed_to_command(self, mock_run):
        bridge = _make_bridge(serial="emulator-5554")
        bridge.devices()
        cmd = mock_run.call_args[0][0]
        assert "-s" in cmd
        assert "emulator-5554" in cmd

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_custom_executable(self, mock_run):
        bridge = _make_bridge(executable="/opt/android/adb")
        bridge.devices()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/opt/android/adb"


# ════════════════════════════════════════════════════════════════════
# EmulatorManager
# ════════════════════════════════════════════════════════════════════

class TestEmulatorManager:
    """AVD lifecycle management."""

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_create_avd(self, mock_run):
        mgr = EmulatorManager()
        result = mgr.create_avd("test_avd", package="system-images;android-34;google_apis;arm64-v8a")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "avdmanager" in cmd[0] or "avdmanager" in " ".join(cmd)
        assert "create" in cmd
        assert "test_avd" in cmd

    @patch("subprocess.run", return_value=_ok_proc("avd1\navd2"))
    def test_list_avds(self, mock_run):
        mgr = EmulatorManager()
        result = mgr.list_avds()
        assert result.ok
        assert "avd1" in result.stdout

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_delete_avd(self, mock_run):
        mgr = EmulatorManager()
        result = mgr.delete_avd("test_avd")
        assert result.ok
        cmd = mock_run.call_args[0][0]
        assert "delete" in cmd

    @patch("subprocess.Popen")
    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_start_returns_bridge(self, mock_run, mock_popen):
        mock_popen.return_value = MagicMock(pid=12345)
        mgr = EmulatorManager()
        bridge = mgr.start("test_avd", headless=True)
        assert isinstance(bridge, AdbBridge)

    @patch("subprocess.run", return_value=_ok_proc(""))
    def test_stop(self, mock_run):
        mgr = EmulatorManager()
        result = mgr.stop("emulator-5554")
        assert result.ok

    @patch("subprocess.run", return_value=_ok_proc("1"))
    def test_wait_for_boot(self, mock_run):
        mgr = EmulatorManager()
        result = mgr.wait_for_boot(serial="emulator-5554", timeout=60)
        assert result.ok


# ════════════════════════════════════════════════════════════════════
# Android Filters
# ════════════════════════════════════════════════════════════════════

class TestAndroidOpen:
    """Launch an app by package name."""

    def test_opens_app_from_constructor(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.start_app.return_value = AdbResult(stdout="Starting: ...", stderr="", returncode=0)
        filt = AndroidOpen(bridge=bridge, package="com.example.app/.MainActivity")
        result = filt.call(Payload())
        assert result.get("android_ok") is True
        assert result.get("android_package") == "com.example.app/.MainActivity"

    def test_opens_app_from_payload(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.start_app.return_value = AdbResult(stdout="ok", stderr="", returncode=0)
        filt = AndroidOpen(bridge=bridge)
        p = Payload().insert("android_package", "com.test/.Main")
        result = filt.call(p)
        assert result.get("android_ok") is True

    def test_raises_without_package(self):
        bridge = MagicMock(spec=AdbBridge)
        filt = AndroidOpen(bridge=bridge)
        with pytest.raises(ValueError, match="android_package"):
            filt.call(Payload())


class TestAndroidClose:
    """Stop an app or kill emulator."""

    def test_stops_app(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.stop_app.return_value = AdbResult(stdout="", stderr="", returncode=0)
        filt = AndroidClose(bridge=bridge, package="com.example.app")
        result = filt.call(Payload())
        assert result.get("android_ok") is True

    def test_stops_from_payload(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.stop_app.return_value = AdbResult(stdout="", stderr="", returncode=0)
        filt = AndroidClose(bridge=bridge)
        p = Payload().insert("android_package", "com.test")
        result = filt.call(p)
        assert result.get("android_ok") is True

    def test_raises_without_package(self):
        bridge = MagicMock(spec=AdbBridge)
        filt = AndroidClose(bridge=bridge)
        with pytest.raises(ValueError, match="android_package"):
            filt.call(Payload())


class TestAndroidTap:
    """Tap at coordinates."""

    def test_tap_from_constructor(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.tap.return_value = AdbResult(stdout="", stderr="", returncode=0)
        filt = AndroidTap(bridge=bridge, x=100, y=200)
        result = filt.call(Payload())
        assert result.get("android_ok") is True

    def test_tap_from_payload(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.tap.return_value = AdbResult(stdout="", stderr="", returncode=0)
        filt = AndroidTap(bridge=bridge)
        p = Payload().insert("android_x", 50).insert("android_y", 75)
        result = filt.call(p)
        assert result.get("android_ok") is True
        bridge.tap.assert_called_once_with(50, 75)

    def test_raises_without_coordinates(self):
        bridge = MagicMock(spec=AdbBridge)
        filt = AndroidTap(bridge=bridge)
        with pytest.raises(ValueError, match="android_x.*android_y"):
            filt.call(Payload())


class TestAndroidType:
    """Type text into focused element."""

    def test_type_from_constructor(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.type_text.return_value = AdbResult(stdout="", stderr="", returncode=0)
        filt = AndroidType(bridge=bridge, text="hello")
        result = filt.call(Payload())
        assert result.get("android_ok") is True

    def test_type_from_payload(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.type_text.return_value = AdbResult(stdout="", stderr="", returncode=0)
        filt = AndroidType(bridge=bridge)
        p = Payload().insert("android_text", "world")
        result = filt.call(p)
        assert result.get("android_ok") is True
        bridge.type_text.assert_called_once_with("world")

    def test_raises_without_text(self):
        bridge = MagicMock(spec=AdbBridge)
        filt = AndroidType(bridge=bridge)
        with pytest.raises(ValueError, match="android_text"):
            filt.call(Payload())


class TestAndroidEval:
    """Execute adb shell command."""

    def test_eval_from_constructor(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.shell.return_value = AdbResult(stdout="42", stderr="", returncode=0)
        filt = AndroidEval(bridge=bridge, command="echo 42")
        result = filt.call(Payload())
        assert result.get("android_eval") == "42"
        assert result.get("android_ok") is True

    def test_eval_from_payload(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.shell.return_value = AdbResult(stdout="ok", stderr="", returncode=0)
        filt = AndroidEval(bridge=bridge)
        p = Payload().insert("android_command", "getprop ro.build.version.sdk")
        result = filt.call(p)
        assert result.get("android_eval") == "ok"

    def test_raises_without_command(self):
        bridge = MagicMock(spec=AdbBridge)
        filt = AndroidEval(bridge=bridge)
        with pytest.raises(ValueError, match="android_command"):
            filt.call(Payload())

    def test_eval_empty_on_failure(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.shell.return_value = AdbResult(stdout="", stderr="error", returncode=1)
        filt = AndroidEval(bridge=bridge, command="bad")
        result = filt.call(Payload())
        assert result.get("android_eval") == ""
        assert result.get("android_ok") is False


class TestAndroidSnapshot:
    """Dump UI hierarchy."""

    def test_snapshot(self):
        xml = '<hierarchy rotation="0"><node /></hierarchy>'
        bridge = MagicMock(spec=AdbBridge)
        bridge.ui_dump.return_value = AdbResult(stdout=xml, stderr="", returncode=0)
        filt = AndroidSnapshot(bridge=bridge)
        result = filt.call(Payload())
        assert result.get("android_snapshot") == xml
        assert result.get("android_ok") is True

    def test_snapshot_empty_on_failure(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.ui_dump.return_value = AdbResult(stdout="", stderr="error", returncode=1)
        filt = AndroidSnapshot(bridge=bridge)
        result = filt.call(Payload())
        assert result.get("android_snapshot") == ""
        assert result.get("android_ok") is False


class TestAndroidScreenshot:
    """Capture screenshot."""

    def test_screenshot_from_constructor(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.screenshot.return_value = AdbResult(stdout="", stderr="", returncode=0)
        filt = AndroidScreenshot(bridge=bridge, path="/tmp/shot.png")
        result = filt.call(Payload())
        assert result.get("android_screenshot") == "/tmp/shot.png"
        assert result.get("android_ok") is True

    def test_screenshot_from_payload(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.screenshot.return_value = AdbResult(stdout="", stderr="", returncode=0)
        filt = AndroidScreenshot(bridge=bridge)
        p = Payload().insert("android_screenshot_path", "/tmp/s.png")
        result = filt.call(p)
        assert result.get("android_screenshot") == "/tmp/s.png"

    def test_screenshot_default_path(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.screenshot.return_value = AdbResult(stdout="", stderr="", returncode=0)
        filt = AndroidScreenshot(bridge=bridge)
        result = filt.call(Payload())
        # Default path should be non-empty
        assert result.get("android_screenshot") != ""
        assert result.get("android_ok") is True


class TestAndroidInstall:
    """Install APK."""

    def test_install_from_constructor(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.install.return_value = AdbResult(stdout="Success", stderr="", returncode=0)
        filt = AndroidInstall(bridge=bridge, apk="/tmp/app.apk")
        result = filt.call(Payload())
        assert result.get("android_ok") is True

    def test_install_from_payload(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.install.return_value = AdbResult(stdout="Success", stderr="", returncode=0)
        filt = AndroidInstall(bridge=bridge)
        p = Payload().insert("android_apk", "/tmp/test.apk")
        result = filt.call(p)
        assert result.get("android_ok") is True

    def test_raises_without_apk(self):
        bridge = MagicMock(spec=AdbBridge)
        filt = AndroidInstall(bridge=bridge)
        with pytest.raises(ValueError, match="android_apk"):
            filt.call(Payload())


class TestAndroidLog:
    """Capture logcat output."""

    def test_log_default(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.logcat.return_value = AdbResult(
            stdout="I/Tag: msg1\nD/Tag: msg2", stderr="", returncode=0,
        )
        filt = AndroidLog(bridge=bridge)
        result = filt.call(Payload())
        assert "msg1" in result.get("android_log")
        assert result.get("android_ok") is True

    def test_log_with_filter(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.logcat.return_value = AdbResult(stdout="filtered", stderr="", returncode=0)
        filt = AndroidLog(bridge=bridge, tag_filter="MyApp:V")
        result = filt.call(Payload())
        assert result.get("android_ok") is True

    def test_log_with_lines(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.logcat.return_value = AdbResult(stdout="line", stderr="", returncode=0)
        filt = AndroidLog(bridge=bridge, lines=50)
        result = filt.call(Payload())
        bridge.logcat.assert_called_once_with(lines=50, tag_filter=None)


class TestAndroidShell:
    """Raw adb shell escape hatch."""

    def test_shell_from_constructor(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.shell.return_value = AdbResult(stdout="/sdcard", stderr="", returncode=0)
        filt = AndroidShell(bridge=bridge, command="pwd")
        result = filt.call(Payload())
        assert result.get("android_shell") == "/sdcard"
        assert result.get("android_ok") is True

    def test_shell_from_payload(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.shell.return_value = AdbResult(stdout="ok", stderr="", returncode=0)
        filt = AndroidShell(bridge=bridge)
        p = Payload().insert("android_shell_cmd", "ls /")
        result = filt.call(p)
        assert result.get("android_shell") == "ok"

    def test_raises_without_command(self):
        bridge = MagicMock(spec=AdbBridge)
        filt = AndroidShell(bridge=bridge)
        with pytest.raises(ValueError, match="android_shell_cmd"):
            filt.call(Payload())

    def test_shell_empty_on_failure(self):
        bridge = MagicMock(spec=AdbBridge)
        bridge.shell.return_value = AdbResult(stdout="", stderr="not found", returncode=127)
        filt = AndroidShell(bridge=bridge, command="bad")
        result = filt.call(Payload())
        assert result.get("android_shell") == ""
        assert result.get("android_ok") is False


# ════════════════════════════════════════════════════════════════════
# Module-level contract checks
# ════════════════════════════════════════════════════════════════════

class TestAndroidModuleContract:
    """Verify the module follows codeupipe conventions."""

    def test_all_exports_are_alphabetical(self):
        import codeupipe.android as mod
        assert mod.__all__ == sorted(mod.__all__)

    def test_all_filters_have_call_method(self):
        filter_classes = [
            AndroidClose, AndroidEval, AndroidInstall, AndroidLog,
            AndroidOpen, AndroidScreenshot, AndroidShell, AndroidSnapshot,
            AndroidTap, AndroidType,
        ]
        for cls in filter_classes:
            assert hasattr(cls, "call"), f"{cls.__name__} missing .call()"

    def test_payload_keys_use_android_prefix(self):
        """Every filter should write keys starting with android_."""
        bridge = MagicMock(spec=AdbBridge)
        bridge.start_app.return_value = AdbResult(stdout="", stderr="", returncode=0)
        filt = AndroidOpen(bridge=bridge, package="com.test/.Main")
        result = filt.call(Payload())
        # Check that all new keys start with android_
        for key in result._data:
            assert key.startswith("android_"), f"Key '{key}' missing android_ prefix"
