"""
codeupipe.android — Android device control via ADB.

Provides CUP Filters that wrap ``adb`` CLI commands for programmatic
Android device and emulator control from pipelines and the ``cup android``
subcommand.

Architecture
------------
- ``AdbBridge`` — subprocess wrapper (single point of contact to ``adb``)
- ``EmulatorManager`` — AVD lifecycle (create, start, stop, list)
- One Filter per Android action (one class per file)

All Android Filters read/write standard Payload keys:

    android_package         : str   — app component (package/activity)
    android_apk             : str   — path to APK file
    android_command         : str   — shell command to execute
    android_eval            : str   — shell command result
    android_log             : str   — logcat output
    android_screenshot      : str   — path to screenshot file
    android_screenshot_path : str   — requested screenshot destination
    android_shell           : str   — raw shell command result
    android_shell_cmd       : str   — raw shell command to run
    android_snapshot        : str   — UI hierarchy XML
    android_text            : str   — text to type
    android_x               : int   — tap X coordinate
    android_y               : int   — tap Y coordinate
    android_output          : str   — raw output from last command
    android_ok              : bool  — whether last command succeeded
"""

from .adb_bridge import AdbBridge
from .adb_result import AdbResult
from .android_close import AndroidClose
from .android_eval import AndroidEval
from .android_install import AndroidInstall
from .android_log import AndroidLog
from .android_open import AndroidOpen
from .android_screenshot import AndroidScreenshot
from .android_shell import AndroidShell
from .android_snapshot import AndroidSnapshot
from .android_tap import AndroidTap
from .android_type import AndroidType
from .emulator_manager import EmulatorManager

__all__ = [
    "AdbBridge",
    "AdbResult",
    "AndroidClose",
    "AndroidEval",
    "AndroidInstall",
    "AndroidLog",
    "AndroidOpen",
    "AndroidScreenshot",
    "AndroidShell",
    "AndroidSnapshot",
    "AndroidTap",
    "AndroidType",
    "EmulatorManager",
]
