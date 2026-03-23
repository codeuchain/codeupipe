# Sideloading the CUP Bridge Extension (Android CRX)

This guide explains how to download and sideload the CRX file on Android Chrome/Edge.

## 📥 Download

The CRX file is available at:
```
https://codeuchain.github.io/codeupipe/platform/cup-bridge-android.crx
```

### Handling Download Security Warnings

**macOS:** When you download, the file may be marked as "unidentified developer" by Gatekeeper. This is normal for unsigned extensions. To allow it:

1. Open **System Preferences** → **Security & Privacy**
2. Find the CRX file in the recent downloads list
3. Click **Open** to confirm you trust it
4. If prompted, enter your macOS password

Alternatively, run in Terminal:
```bash
xattr -d com.apple.quarantine ~/Downloads/cup-bridge-android.crx
```

**Windows/Linux:** No special handling required; proceed to installation.

---

## 🔐 Extension ID (Stable Across Builds)

Your CRX has a **persistent extension ID**:
```
jjjnodfpbpojcnogdkidclbjcpcjlmma
```

This ID is cryptographically derived from the signing key and remains the same across all CUP Bridge releases. Use this ID to identify the extension in your browser's extension management pages.

---

## 📱 Sideload on Android Chrome

### Prerequisites
- **Android 5.0+** with Chrome/Edge installed
- Developer Mode enabled on your device (Android Settings → Developer Options)
- USB cable connected to your computer (for some methods)

### Method 1: Manual Install via Edge (Easiest)

**Microsoft Edge on Android** has native CRX sideload support:

1. Download the `.crx` file (from link above)
2. Open **Edge** → **Settings** → **Developer Settings**
3. Enable **Enable extension** (toggle)
4. Tap **+** to add an extension
5. Select the downloaded CRX file

The extension will install and appear in your Edge sidebar.

### Method 2: Chrome **via Adb** (Requires PC/Mac)

Chrome on Android doesn't have a built-in UI to install CRX files directly. Use **adb** (Android Debug Bridge):

1. **Install adb** (comes with Android Studio, or install via Homebrew):
   ```bash
   # macOS
   brew install android-platform-tools
   
   # Linux
   sudo apt install android-sdk-platform-tools
   ```

2. **Enable USB Debugging** on your Android device:
   - Settings → Developer Options → USB Debugging (ON)

3. **Connect device** and authorize the connection

4. **Push the CRX** file to your device:
   ```bash
   adb push ~/Downloads/cup-bridge-android.crx /sdcard/Download/
   ```

5. **On Android**, open **Chrome** → **Settings** → **Advanced** → **Experiments**
   - Search for `enable-external-extensions-for-unsandboxed-pages`
   - Enable it

6. **Sideload via ADB**:
   ```bash
   adb shell am start -action android.intent.action.VIEW \
     -d "file:///sdcard/Download/cup-bridge-android.crx" \
     -t "application/x-chrome-extension" com.android.chrome
   ```

The extension will prompt you to confirm installation.

---

## 🔍 Verify Installation

After installation, check that CUP Bridge appears in your extension list:

**Edge (Android):**
- Tap the **Extensions** icon (puzzle piece) in the sidebar
- Look for "CUP Bridge" in the list

**Chrome (via adb):**
- Navigate to `chrome://extensions/`
- Find the extension ID: `jjjnodfpbpojcnogdkidclbjcpcjlmma`
- Verify **Enabled** is toggled ON

---

## ❌ Troubleshooting

### "File Download Was Blocked"

**Cause:** Your browser or system is treating the unsigned CRX as suspicious.

**Solution:**
- **macOS:** Use the `xattr` command above to remove quarantine flags
- **Windows:** Right-click the file → Properties → Unblock → OK
- **Android:** Ensure "Unknown Sources" or equivalent is enabled in security settings

### CRX Disappears After Download

**Cause:** macOS Gatekeeper or browser auto-cleanup removing suspicious files.

**Solution:**
1. **Approve the file** in macOS Security settings (see above)
2. **Use a different browser** — Safari and Edge handle unsigned extensions more gracefully than Chrome
3. **Save to Desktop** instead of Downloads folder (less aggressive cleanup)

### "Extension Install Failed" on Android

**Cause:** 
- Device time is incorrect (affects signature validation)
- CRX is corrupted (incomplete download)

**Solution:**
- Set device time/date correctly (Settings → Date & Time → Auto)
- Re-download the CRX
- Try a different sideload method (adb vs Edge UI)

### Extension Is "Disabled" or "Not Running"

**Cause:** Extension needs explicit permission on your device.

**Solution:**
1. Press and hold the extension in your extension menu
2. Tap **Permissions** and grant the required access
3. Toggle **Enabled** ON

---

## 🛡️ Security Notes

- **CRX Signing:** This CRX is signed with a persistent 2048-bit RSA key, ensuring its identity is stable across releases.
- **Code Transparency:** The source code is open-source at [github.com/orchestrate-solutions/codeupipe](https://github.com/orchestrate-solutions/codeupipe)
- **Permissions:** CUP Bridge requests minimal permissions (see `manifest.android.json` for details)
- **Android Mode:** The Android CRX disables native messaging (unavailable) and falls back to WebAssembly tier automatically

---

## 📋 Advanced: Building Your Own CRX

To build a custom CRX with your own signing key:

```bash
cd codeupipe/connect/extension
python3 build_crx.py . --out custom-cup-bridge.crx --key my-key.pem
```

This changes the extension ID but maintains full feature compatibility.

---

**Need help?** File an issue at [github.com/orchestrate-solutions/codeupipe/issues](https://github.com/orchestrate-solutions/codeupipe/issues)
