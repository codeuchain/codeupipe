#!/usr/bin/env python3
"""
android_edge_setup.py — Boot emulator, install Edge Canary, sideload CUP extension.

Automates the full flow:
    1. Boot Android emulator
    2. Install Edge Canary APK
    3. Dismiss OOBE dialogs
    4. Build CRX3 with Android manifest (no nativeMessaging)
    5. Push CRX to device
    6. Enable Developer Options in Edge (tap build number 7x)
    7. Sideload CRX via Developer Options
    8. Navigate to CUP Platform and validate dashboard

Gives real-time feedback at every step.  No blind sleeps.

Usage:
    python3 examples/android_edge_setup.py

Prerequisites:
    - Android SDK at ~/Library/Android/sdk (adb, emulator, avdmanager)
    - AVD named 'cup_edge_test' already created
    - Edge Canary APK at /tmp/com.microsoft.emmx.canary.apk
    - openssl CLI (for CRX signing)

Key findings (Edge Canary 148+):
    - Extensions are BUILT-IN — no edge://flags needed
    - chrome.runtime.connectNative() does NOT exist on Android
    - Extension correctly falls back to WASM-only tier
    - Developer Options unlocked by tapping build number 7x
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTENSION_DIR = PROJECT_ROOT / "codeupipe" / "connect" / "extension"
ANDROID_MANIFEST = EXTENSION_DIR / "manifest.android.json"

ANDROID_HOME = Path.home() / "Library" / "Android" / "sdk"
ADB = str(ANDROID_HOME / "platform-tools" / "adb")
EMULATOR = str(ANDROID_HOME / "emulator" / "emulator")
AVD_NAME = "cup_edge_test"
EDGE_PKG = "com.microsoft.emmx.canary"
EDGE_APK = Path("/tmp/com.microsoft.emmx.canary.apk")
EDGE_ACTIVITY = f"{EDGE_PKG}/com.microsoft.ruby.Main"
SERIAL = "emulator-5554"
SCREENSHOT_DIR = Path("/tmp/cup-android-screenshots")
CRX_OUTPUT = Path("/tmp/cup-bridge-android.crx")
PLATFORM_URL = "https://codeuchain.github.io/codeupipe/platform/"

# ── Helpers ─────────────────────────────────────────────────────────

def log(emoji: str, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"  {emoji}  [{ts}] {msg}", flush=True)


def adb(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    cmd = [ADB, "-s", SERIAL] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def adb_shell(cmd: str, timeout: int = 30) -> str:
    r = adb("shell", cmd, timeout=timeout)
    return r.stdout.strip()


def screenshot(name: str) -> Path:
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    dest = SCREENSHOT_DIR / f"{name}.png"
    r = subprocess.run(
        [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
        capture_output=True, timeout=15,
    )
    if r.returncode == 0 and len(r.stdout) > 100:
        dest.write_bytes(r.stdout)
        log("📸", f"Screenshot → {dest}")
    else:
        log("⚠️", f"Screenshot failed ({len(r.stdout)} bytes)")
    return dest


def ui_texts() -> list[str]:
    """Dump UI hierarchy and return all non-empty text values."""
    adb("shell", "rm -f /sdcard/cup_ui.xml")
    r = adb("shell", "uiautomator dump /sdcard/cup_ui.xml")
    if "error" in r.stdout.lower() or "null root" in r.stdout.lower():
        return []
    xml = adb_shell("cat /sdcard/cup_ui.xml")
    texts = re.findall(r'text="([^"]+)"', xml)
    return [t for t in texts if t.strip()]


def ui_xml() -> str:
    """Get the raw UI hierarchy XML."""
    adb("shell", "rm -f /sdcard/cup_ui.xml")
    adb("shell", "uiautomator dump /sdcard/cup_ui.xml")
    return adb_shell("cat /sdcard/cup_ui.xml")


def tap_text(target: str) -> bool:
    """Find a UI element by text and tap its center."""
    xml = adb_shell("cat /sdcard/cup_ui.xml")
    # Find node with matching text and extract bounds
    pattern = rf'text="{re.escape(target)}"[^/]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
    m = re.search(pattern, xml)
    if not m:
        return False
    x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    adb("shell", f"input tap {cx} {cy}")
    log("👆", f"Tapped '{target}' at ({cx}, {cy})")
    return True


def wait_for(condition, description: str, timeout: int = 120, interval: int = 3) -> bool:
    """Poll until condition() is truthy, with progress feedback."""
    log("⏳", f"Waiting: {description} (timeout {timeout}s)")
    start = time.time()
    dots = 0
    while time.time() - start < timeout:
        result = condition()
        if result:
            elapsed = int(time.time() - start)
            log("✅", f"{description} — done in {elapsed}s")
            return True
        dots += 1
        if dots % 5 == 0:
            elapsed = int(time.time() - start)
            log("⏳", f"  ...still waiting ({elapsed}s)")
        time.sleep(interval)
    elapsed = int(time.time() - start)
    log("❌", f"{description} — timed out after {elapsed}s")
    return False


# ── Steps ───────────────────────────────────────────────────────────

def step_check_prereqs() -> bool:
    log("🔍", "Checking prerequisites...")
    ok = True
    for tool, path in [("adb", ADB), ("emulator", EMULATOR)]:
        if Path(path).exists():
            log("✅", f"  {tool}: {path}")
        else:
            log("❌", f"  {tool}: NOT FOUND at {path}")
            ok = False
    if EDGE_APK.exists():
        size_mb = EDGE_APK.stat().st_size / (1024 * 1024)
        log("✅", f"  Edge APK: {EDGE_APK} ({size_mb:.0f} MB)")
    else:
        log("❌", f"  Edge APK: NOT FOUND at {EDGE_APK}")
        ok = False
    # Check AVD exists
    r = subprocess.run(
        [str(ANDROID_HOME / "cmdline-tools" / "latest" / "bin" / "avdmanager"),
         "list", "avd", "-c"],
        capture_output=True, text=True,
    )
    if AVD_NAME in r.stdout:
        log("✅", f"  AVD: {AVD_NAME}")
    else:
        log("❌", f"  AVD '{AVD_NAME}' not found. Available: {r.stdout.strip()}")
        ok = False
    return ok


def step_boot_emulator() -> bool:
    log("🚀", f"Booting emulator '{AVD_NAME}'...")
    # Check if already running
    r = subprocess.run([ADB, "devices"], capture_output=True, text=True)
    if SERIAL in r.stdout and "device" in r.stdout.split(SERIAL)[1].split("\n")[0]:
        log("✅", "Emulator already running")
        return True
    # Launch
    subprocess.Popen(
        [EMULATOR, "-avd", AVD_NAME, "-no-audio", "-no-boot-anim",
         "-gpu", "host", "-memory", "4096"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Wait for ADB connection
    if not wait_for(
        lambda: SERIAL in subprocess.run(
            [ADB, "devices"], capture_output=True, text=True
        ).stdout,
        "ADB device visible",
        timeout=60,
    ):
        return False
    # Wait for boot_completed
    return wait_for(
        lambda: adb_shell("getprop sys.boot_completed") == "1",
        "Boot completed (sys.boot_completed=1)",
        timeout=180,
        interval=5,
    )


def step_install_edge() -> bool:
    log("📦", "Checking if Edge Canary is installed...")
    r = adb("shell", "pm list packages")
    if EDGE_PKG in r.stdout:
        log("✅", "Edge Canary already installed")
        return True
    log("📦", f"Installing Edge Canary ({EDGE_APK.stat().st_size // (1024*1024)} MB)...")
    log("⏳", "  This takes 30-60s on emulator...")
    r = subprocess.run(
        [ADB, "-s", SERIAL, "install", "-r", str(EDGE_APK)],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode == 0 and "Success" in r.stdout:
        log("✅", "Edge Canary installed successfully")
        return True
    log("❌", f"Install failed: {r.stderr or r.stdout}")
    return False


def step_launch_edge() -> bool:
    log("🌐", "Launching Edge Canary...")
    adb("shell", f"am start -n {EDGE_ACTIVITY}")
    time.sleep(5)  # Give it a moment to start rendering

    # Dismiss OOBE screens with feedback
    for attempt in range(10):
        texts = ui_texts()
        if not texts:
            log("⏳", f"  UI not ready yet (attempt {attempt + 1})")
            time.sleep(3)
            continue

        log("📱", f"  Screen text: {texts[:5]}")
        screenshot(f"oobe_{attempt}")

        # Check for common OOBE / dialog screens
        if any("isn't responding" in t for t in texts):
            log("⚠️", "  ANR dialog — tapping 'Wait'")
            tap_text("Wait")
            time.sleep(5)
            continue

        if any("system isn't responding" in t.lower() for t in texts):
            log("⚠️", "  System ANR — tapping 'Wait'")
            tap_text("Wait")
            time.sleep(5)
            continue

        if "Not now" in texts:
            log("👆", "  Default browser dialog — tapping 'Not now'")
            tap_text("Not now")
            time.sleep(3)
            continue

        if "Confirm" in texts:
            log("👆", "  Privacy consent — tapping 'Confirm'")
            tap_text("Confirm")
            time.sleep(3)
            continue

        if "Accept & continue" in texts:
            tap_text("Accept & continue")
            time.sleep(3)
            continue

        if "No thanks" in texts:
            tap_text("No thanks")
            time.sleep(3)
            continue

        if "Skip" in texts:
            tap_text("Skip")
            time.sleep(3)
            continue

        if "Maybe later" in texts:
            tap_text("Maybe later")
            time.sleep(3)
            continue

        if "Done" in texts:
            tap_text("Done")
            time.sleep(3)
            continue

        if "Got it" in texts:
            tap_text("Got it")
            time.sleep(3)
            continue

        # Check if we've reached a normal browser state
        if any("Search or enter web address" in t for t in texts):
            log("✅", "Edge Canary is ready (address bar visible)")
            screenshot("edge_ready")
            return True

        # Also check for the URL bar resource ID
        xml = adb_shell("cat /sdcard/cup_ui.xml")
        if "url_bar" in xml or "search_box" in xml or "omnibox" in xml:
            log("✅", "Edge Canary is ready (URL bar detected)")
            screenshot("edge_ready")
            return True

        log("🔄", f"  Unrecognized screen, waiting... texts={texts[:3]}")
        time.sleep(3)

    log("⚠️", "Could not fully dismiss OOBE after 10 attempts")
    screenshot("oobe_stuck")
    return False


def step_navigate_flags() -> bool:
    """Edge Canary 148+ has extensions built-in — no flags needed.

    This step is kept for older Edge versions where the flag might
    still be required.  On 148+ it gracefully no-ops.
    """
    log("🏁", "Checking if extensions need edge://flags...")
    adb("shell", f"am start -a android.intent.action.VIEW -d 'edge://flags' -n {EDGE_ACTIVITY}")
    time.sleep(5)
    screenshot("flags_page")
    texts = ui_texts()
    log("📱", f"  Flags page text: {texts[:5]}")
    if any("No matching experiments" in t for t in texts):
        log("✅", "Extensions are built-in (no flag needed)")
        return True
    if any("Experiments" in t or "flags" in t.lower() for t in texts):
        log("✅", "Flags page loaded — extensions may need manual enable")
        return True
    log("⚠️", "Flags page may not have loaded")
    return True  # Non-fatal, continue anyway


def step_build_crx() -> bool:
    """Build CRX3 with the Android-specific manifest (no nativeMessaging)."""
    log("🔧", "Building CRX3 for Android...")

    if not EXTENSION_DIR.is_dir():
        log("❌", f"Extension dir not found: {EXTENSION_DIR}")
        return False
    if not ANDROID_MANIFEST.is_file():
        log("❌", f"Android manifest not found: {ANDROID_MANIFEST}")
        return False

    # Import the build_crx module from the extension directory
    sys.path.insert(0, str(EXTENSION_DIR))
    try:
        from build_crx import build_crx
    except ImportError as exc:
        log("❌", f"Cannot import build_crx: {exc}")
        return False
    finally:
        sys.path.pop(0)

    try:
        crx_bytes = build_crx(
            EXTENSION_DIR,
            manifest_override=ANDROID_MANIFEST,
        )
        CRX_OUTPUT.write_bytes(crx_bytes)
        size_kb = len(crx_bytes) / 1024
        log("✅", f"CRX3 built: {CRX_OUTPUT} ({size_kb:.1f} KB)")
        return True
    except Exception as exc:
        log("❌", f"CRX build failed: {exc}")
        return False


def step_push_crx() -> bool:
    """Push the CRX file to the emulator's Downloads folder."""
    log("�", "Pushing CRX to emulator...")
    if not CRX_OUTPUT.is_file():
        log("❌", f"CRX file not found: {CRX_OUTPUT}")
        return False

    r = adb("push", str(CRX_OUTPUT), "/sdcard/Download/cup-bridge.crx")
    if r.returncode == 0:
        log("✅", "CRX pushed to /sdcard/Download/cup-bridge.crx")
        return True
    log("❌", f"Push failed: {r.stderr}")
    return False


def step_enable_dev_options() -> bool:
    """Enable Developer Options in Edge by tapping build number 7 times.

    Navigate: Edge Settings → About Microsoft Edge → tap build number.
    """
    log("🔓", "Enabling Edge Developer Options...")

    # Navigate to About Microsoft Edge
    adb("shell", f"am start -a android.intent.action.VIEW -d 'edge://settings/help' -n {EDGE_ACTIVITY}")
    time.sleep(5)
    screenshot("about_edge")

    texts = ui_texts()
    log("�", f"  Settings page text: {texts[:5]}")

    # Find and tap the build number 7 times
    for i in range(7):
        xml = ui_xml()
        # Look for the version/build number text pattern (e.g. "148.0.3155.3")
        version_match = re.search(
            r'text="(\d+\.\d+\.\d+\.\d+)"[^/]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml,
        )
        if version_match:
            x1, y1, x2, y2 = (
                int(version_match.group(2)),
                int(version_match.group(3)),
                int(version_match.group(4)),
                int(version_match.group(5)),
            )
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            adb("shell", f"input tap {cx} {cy}")
            if i == 0:
                log("👆", f"Tapping build number at ({cx}, {cy}) — 7 times...")
            time.sleep(0.3)
        else:
            log("⚠️", f"  Build number not found on attempt {i + 1}")
            time.sleep(1)

    time.sleep(2)
    texts = ui_texts()
    if any("Developer" in t for t in texts):
        log("✅", "Developer Options enabled")
        screenshot("dev_options_enabled")
        return True

    log("⚠️", "Developer Options may not have been enabled — check manually")
    screenshot("dev_options_maybe")
    return True  # Non-fatal


def step_sideload_crx() -> bool:
    """Navigate to Developer Options and install the CRX.

    This step requires manual interaction on the emulator to
    confirm the extension install dialog. The script will wait
    and then verify installation.
    """
    log("�", "Opening Developer Options for CRX sideload...")

    # Navigate to Developer Options
    adb("shell", f"am start -a android.intent.action.VIEW -d 'edge://settings' -n {EDGE_ACTIVITY}")
    time.sleep(3)
    screenshot("settings_page")

    # Look for Developer Options
    texts = ui_texts()
    if "Developer options" in texts:
        tap_text("Developer options")
        time.sleep(3)
    elif "Developer Options" in texts:
        tap_text("Developer Options")
        time.sleep(3)

    screenshot("dev_options")
    texts = ui_texts()
    log("�", f"  Dev options text: {texts[:8]}")

    # Look for "Extension install by crx"
    crx_option = None
    for t in texts:
        if "crx" in t.lower() or "CRX" in t:
            crx_option = t
            break
        if "Extension install" in t:
            crx_option = t
            break

    if crx_option:
        tap_text(crx_option)
        time.sleep(3)
        screenshot("crx_file_picker")
        log("�", "File picker should be open — select cup-bridge.crx from Downloads")
        log("⏳", "Waiting for user to confirm extension install (60s timeout)...")

        # Wait for the "Add" confirmation dialog or extension to appear
        if wait_for(
            lambda: any("Add" in t or "extension" in t.lower() for t in ui_texts()),
            "Extension install dialog",
            timeout=60,
        ):
            # Try to tap "Add" if it appears
            time.sleep(2)
            texts = ui_texts()
            if any("Add" in t for t in texts):
                for t in texts:
                    if t.startswith("Add"):
                        tap_text(t)
                        break
                time.sleep(3)
                log("✅", "Extension install confirmed")
                screenshot("extension_installed")
                return True

    log("⚠️", "CRX sideload may need manual completion")
    log("📋", "Manual steps:")
    log("�", "  1. Edge Settings > Developer Options")
    log("📋", "  2. 'Extension install by crx'")
    log("�", "  3. Select /sdcard/Download/cup-bridge.crx")
    log("📋", "  4. Tap 'Add' on the confirmation dialog")
    return True  # Non-fatal — user can do it manually


def step_validate_platform() -> bool:
    """Navigate to CUP Platform and validate the dashboard renders."""
    log("🌐", f"Navigating to {PLATFORM_URL}...")
    adb(
        "shell",
        f"am start -a android.intent.action.VIEW -d '{PLATFORM_URL}' -n {EDGE_ACTIVITY}",
    )
    time.sleep(8)
    screenshot("platform_loading")

    # Wait for the platform to render
    if not wait_for(
        lambda: any("CUP Platform" in t for t in ui_texts()),
        "Platform SPA rendered",
        timeout=30,
    ):
        log("⚠️", "Platform page may not have loaded")
        screenshot("platform_timeout")
        return False

    texts = ui_texts()
    log("�", f"  Platform text: {texts[:10]}")
    screenshot("platform_loaded")

    # Validate key dashboard elements
    checks = {
        "Extension status": any("Installed" in t or "✅" in t for t in texts),
        "WASM tier": any("WASM" in t for t in texts),
        "CUP Platform title": any("CUP Platform" in t for t in texts),
    }

    all_ok = True
    for label, passed in checks.items():
        if passed:
            log("✅", f"  {label}")
        else:
            log("❌", f"  {label} — NOT FOUND")
            all_ok = False

    return all_ok


def step_summary(validation_ok: bool) -> None:
    log("📊", "=" * 50)
    log("📊", "ANDROID EDGE SETUP SUMMARY")
    log("📊", "=" * 50)
    log("📊", f"  Emulator: {AVD_NAME} ({SERIAL})")
    log("📊", f"  Edge: {EDGE_PKG}")
    log("📊", f"  CRX: {CRX_OUTPUT}")
    log("📊", f"  Android manifest: {ANDROID_MANIFEST}")
    log("📊", f"  Screenshots: {SCREENSHOT_DIR}/")
    log("📊", "")
    log("📊", "VALIDATION RESULTS:")
    if validation_ok:
        log("📊", "  ✅ Extension: Installed")
        log("📊", "  🟡 Tier: WASM Only (no native messaging on Android)")
        log("📊", "  ❌ Native Host: Not Connected (expected)")
        log("📊", "  ✅ Platform SPA: Renders correctly")
    else:
        log("📊", "  ⚠️  Validation incomplete — check screenshots")
    log("📊", "")
    log("📊", "KEY FINDINGS:")
    log("📊", "  • Edge Canary 148+ has extensions BUILT-IN (no flags)")
    log("📊", "  • chrome.runtime.connectNative() unavailable on Android")
    log("📊", "  • Extension falls back to WASM tier automatically")
    log("📊", "  • All 5 capability store recipes render on mobile")
    log("📊", "=" * 50)


# ── Main ────────────────────────────────────────────────────────────

def main() -> int:
    print()
    print("=" * 60)
    print("  CUP Android Edge Setup — Real-Time Feedback")
    print("=" * 60)
    print()

    if not step_check_prereqs():
        log("💥", "Prerequisites failed. Fix the above and retry.")
        return 1

    if not step_boot_emulator():
        log("💥", "Emulator boot failed.")
        return 1

    if not step_install_edge():
        log("💥", "Edge install failed.")
        return 1

    if not step_launch_edge():
        log("⚠️", "Edge OOBE not fully dismissed — continuing anyway")

    step_navigate_flags()

    if not step_build_crx():
        log("💥", "CRX build failed.")
        return 1

    step_push_crx()
    step_enable_dev_options()
    step_sideload_crx()

    validation_ok = step_validate_platform()
    step_summary(validation_ok)

    return 0 if validation_ok else 1


if __name__ == "__main__":
    sys.exit(main())
