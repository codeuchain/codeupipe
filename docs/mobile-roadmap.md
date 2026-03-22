# CUP Mobile — Device Bridge Roadmap

!!! info "Status: Planned"
    CUP Mobile is a planned product. The architecture is designed,
    the integration points are identified, and the CUP Browser SDK
    provides the template pattern. No implementation yet.

## Vision

Control mobile devices the same way CUP Browser controls browsers.
A `MobileBridge` that speaks ADB (Android) or libimobiledevice (iOS),
exposed as CUP Filters, composable in Pipelines, testable in isolation.

```
cup mobile open com.example.app     →  MobileOpen filter
cup mobile tap 540 960              →  MobileTap filter
cup mobile screenshot               →  MobileScreenshot filter
cup mobile shell "pm list packages" →  MobileShell filter
cup mobile close                    →  MobileClose filter
```

## Architecture

```
CUP Mobile
├── codeupipe/mobile/
│   ├── __init__.py
│   ├── bridge.py              ← MobileBridge (ADB/libimobiledevice)
│   ├── adb_bridge.py          ← Android implementation
│   ├── ios_bridge.py          ← iOS implementation
│   ├── mobile_open.py         ← Launch / focus an app
│   ├── mobile_tap.py          ← Tap coordinates or element
│   ├── mobile_swipe.py        ← Swipe gesture
│   ├── mobile_fill.py         ← Text input
│   ├── mobile_screenshot.py   ← Capture screen
│   ├── mobile_shell.py        ← Run shell command on device
│   ├── mobile_snapshot.py     ← UI hierarchy (like a11y tree)
│   └── mobile_close.py        ← Close app / disconnect
├── codeupipe/cli/commands/
│   └── mobile_cmds.py         ← `cup mobile` CLI
└── tests/
    ├── test_mobile_bridge.py
    └── test_mobile_filters.py
```

### Bridge Pattern (same as PlaywrightBridge)

```python
from codeupipe.mobile import AdbBridge, MobileOpen, MobileScreenshot

with AdbBridge(device="emulator-5554") as bridge:
    p = Payload()
    p = MobileOpen(bridge=bridge, package="com.example.app").call(p)
    p = MobileScreenshot(bridge=bridge, path="screen.png").call(p)
    assert p.get("mobile_ok") is True
```

### Integration with CUP Browser

The real power is composing mobile + browser in one Pipeline:

```python
# Phone controls the TV (via browser)
pipeline = Pipeline()
pipeline.add_filter(MobileOpen(mobile_bridge, package="com.remote.app"))
pipeline.add_filter(MobileTap(mobile_bridge, x=200, y=400))  # tap "Cast"
pipeline.add_filter(BrowserEval(browser_bridge, expression="checkCastStatus()"))
```

### Integration with CUP Bridge Extension

The extension could detect connected devices and expose them:

```javascript
// From the platform site
const devices = await window.cupBridge.listDevices();
// → [{type: "android", serial: "abc123", model: "Pixel 8"}]

await window.cupBridge.mobileExec("abc123", "input tap 540 960");
```

## Transport Layers

### Android (ADB)

| Method | Description |
|--------|-------------|
| USB | Direct USB connection, `adb devices` |
| Wi-Fi | `adb connect <ip>:5555` |
| Wireless Debug | Android 11+ pairing |

ADB provides: shell access, screen capture, input injection, package
management, logcat, file push/pull. All synchronous CLI calls — perfect
for the CUP Filter pattern.

### iOS (libimobiledevice)

| Method | Description |
|--------|-------------|
| USB | Via `idevice_id`, `ideviceinfo` |
| Wi-Fi | Network pairing after initial USB trust |

More limited than ADB. Screen capture via `idevicescreenshot`.
App install/launch via `ideviceinstaller`. No direct input injection —
requires XCUITest or Appium bridge for tap/swipe.

### Remote (future)

```
Device → CUP Bridge Extension → Native Host → adb/libimobiledevice → Device
```

This enables remote device control from any browser tab, not just
the machine physically connected to the device.

## Milestones

| Phase | Scope | Dependencies |
|-------|-------|-------------|
| 1 | `AdbBridge` + 6 core filters + CLI | adb on PATH |
| 2 | E2E tests with Android emulator | Android SDK |
| 3 | `IosBridge` + core filters | libimobiledevice |
| 4 | Extension integration (list/control devices) | CUP Bridge Extension |
| 5 | Remote device via bridge relay | Phase 1 + 4 |

## Why This Fits CUP

- **Same pattern**: Bridge → Filters → Pipeline → CLI. Identical to
  CUP Browser. No new abstractions.
- **Composable**: Mobile filters mix with browser filters, AI filters,
  deploy filters — all in one Pipeline.
- **Testable**: Mock the bridge, test the filter. Same `run_filter()`
  + `assert_payload()` helpers.
- **Dogfoodable**: Use `cup mobile` to test mobile apps the same way
  we use `cup browser` to test web apps.
