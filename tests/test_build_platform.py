"""Tests for the build_platform MkDocs hook.

Verifies that the hook correctly copies platform SPA files, recipes,
and builds a valid extension zip into the site output directory.
"""

import json
import zipfile
from pathlib import Path

import pytest

# ── Import the hook functions directly ───────────────────────────────

import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "hooks"))

from build_platform import on_post_build, _build_extension_zip  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def fake_config(tmp_path):
    """Fake MkDocs config pointing at the real project with tmp site_dir."""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    return {
        "config_file_path": str(_PROJECT_ROOT / "mkdocs.yml"),
        "site_dir": str(site_dir),
    }


# ── Tests: SPA file copying ─────────────────────────────────────────

class TestPlatformBuildHook:
    """Verify that on_post_build produces the correct site/platform/ layout."""

    def test_platform_dir_created(self, fake_config, tmp_path):
        on_post_build(fake_config)
        platform = Path(fake_config["site_dir"]) / "platform"
        assert platform.is_dir()

    def test_index_html_copied(self, fake_config):
        on_post_build(fake_config)
        f = Path(fake_config["site_dir"]) / "platform" / "index.html"
        assert f.exists()
        content = f.read_text()
        assert "CUP Platform" in content

    def test_platform_js_copied(self, fake_config):
        on_post_build(fake_config)
        f = Path(fake_config["site_dir"]) / "platform" / "platform.js"
        assert f.exists()
        content = f.read_text()
        assert "CupPlatform" in content

    def test_store_js_copied(self, fake_config):
        on_post_build(fake_config)
        f = Path(fake_config["site_dir"]) / "platform" / "store.js"
        assert f.exists()

    def test_dashboard_js_copied(self, fake_config):
        on_post_build(fake_config)
        f = Path(fake_config["site_dir"]) / "platform" / "dashboard.js"
        assert f.exists()

    def test_platform_css_copied(self, fake_config):
        on_post_build(fake_config)
        f = Path(fake_config["site_dir"]) / "platform" / "platform.css"
        assert f.exists()
        content = f.read_text()
        assert "--bg:" in content


# ── Tests: Recipes ───────────────────────────────────────────────────

class TestPlatformRecipes:
    """Verify recipes are copied (symlink resolved) into site/platform/recipes/."""

    def test_recipes_dir_created(self, fake_config):
        on_post_build(fake_config)
        recipes = Path(fake_config["site_dir"]) / "platform" / "recipes"
        assert recipes.is_dir()

    def test_manifest_json_copied(self, fake_config):
        on_post_build(fake_config)
        f = Path(fake_config["site_dir"]) / "platform" / "recipes" / "manifest.json"
        assert f.exists()
        data = json.loads(f.read_text())
        assert "capabilities" in data

    def test_dream_training_recipe(self, fake_config):
        on_post_build(fake_config)
        f = Path(fake_config["site_dir"]) / "platform" / "recipes" / "dream-training.json"
        assert f.exists()
        data = json.loads(f.read_text())
        assert data["id"] == "dream-training"

    def test_all_recipes_present(self, fake_config):
        on_post_build(fake_config)
        recipes = Path(fake_config["site_dir"]) / "platform" / "recipes"
        names = {f.name for f in recipes.iterdir() if f.is_file()}
        expected = {
            "manifest.json",
            "dream-training.json",
            "onnx-inference.json",
            "browser-training.json",
            "swarm-training.json",
            "job-queue.json",
        }
        assert expected.issubset(names), f"Missing: {expected - names}"

    def test_recipe_count_at_least_five(self, fake_config):
        on_post_build(fake_config)
        recipes = Path(fake_config["site_dir"]) / "platform" / "recipes"
        json_files = [f for f in recipes.iterdir() if f.suffix == ".json" and f.name != "manifest.json"]
        assert len(json_files) >= 5


# ── Tests: Extension Zip ────────────────────────────────────────────

class TestExtensionZip:
    """Verify the extension zip is a valid, loadable Chrome extension."""

    def test_zip_created(self, fake_config):
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        assert z.exists()
        assert z.stat().st_size > 1000

    def test_zip_contains_manifest(self, fake_config):
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            assert "manifest.json" in zf.namelist()

    def test_zip_manifest_valid_json(self, fake_config):
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            data = json.loads(zf.read("manifest.json"))
            assert data["manifest_version"] == 3
            assert data["name"] == "CUP Platform Bridge"

    def test_zip_contains_service_worker(self, fake_config):
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            assert "service-worker.js" in zf.namelist()

    def test_zip_contains_content_script(self, fake_config):
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            assert "content-script.js" in zf.namelist()

    def test_zip_contains_popup(self, fake_config):
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            assert "popup.html" in zf.namelist()

    def test_zip_contains_cup_bridge_api(self, fake_config):
        """MAIN world script must be in the zip for CSP bypass."""
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            assert "cup-bridge-api.js" in zf.namelist()

    def test_zip_manifest_declares_main_world(self, fake_config):
        """Manifest must have a content_scripts entry with world=MAIN for cup-bridge-api.js."""
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            entries = manifest.get("content_scripts", [])
            assert len(entries) == 2, f"Expected 2 content_scripts entries, got {len(entries)}"
            main_entry = entries[1]
            assert main_entry.get("world") == "MAIN"
            assert "cup-bridge-api.js" in main_entry.get("js", [])

    def test_zip_contains_icons_in_correct_path(self, fake_config):
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            names = zf.namelist()
            assert "icons/icon-16.png" in names
            assert "icons/icon-48.png" in names
            assert "icons/icon-128.png" in names

    def test_zip_contains_recipes(self, fake_config):
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            names = zf.namelist()
            assert "recipes/manifest.json" in names
            assert "recipes/dream-training.json" in names

    def test_zip_contains_native_host(self, fake_config):
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            names = zf.namelist()
            assert "native/native_host.py" in names
            assert "native/install-native.sh" in names
            assert "native/com.codeupipe.bridge.json" in names

    def test_zip_icon_paths_match_manifest(self, fake_config):
        """Manifest icon paths must reference files that exist in the zip."""
        on_post_build(fake_config)
        z = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-extension.zip"
        with zipfile.ZipFile(str(z)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            names = set(zf.namelist())

            # Check action.default_icon
            for size, path in manifest.get("action", {}).get("default_icon", {}).items():
                assert path in names, f"Icon {path} (size {size}) not in zip"

            # Check top-level icons
            for size, path in manifest.get("icons", {}).items():
                assert path in names, f"Icon {path} (size {size}) not in zip"


# ── Tests: Standalone zip builder ────────────────────────────────────

class TestBuildExtensionZipDirect:
    """Test _build_extension_zip as a standalone function."""

    def test_builds_from_extension_dir(self, tmp_path):
        ext_src = _PROJECT_ROOT / "codeupipe" / "connect" / "extension"
        zip_path = tmp_path / "test.zip"
        _build_extension_zip(ext_src, zip_path)
        assert zip_path.exists()
        with zipfile.ZipFile(str(zip_path)) as zf:
            assert "manifest.json" in zf.namelist()
            assert len(zf.namelist()) >= 10


# ── Tests: Android CRX ──────────────────────────────────────────────

class TestAndroidCrx:
    """Verify the Android CRX is produced and valid."""

    def test_crx_created(self, fake_config):
        on_post_build(fake_config)
        crx = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-android.crx"
        assert crx.exists()
        assert crx.stat().st_size > 1000

    def test_crx_magic_bytes(self, fake_config):
        on_post_build(fake_config)
        crx = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-android.crx"
        data = crx.read_bytes()
        assert data[:4] == b"Cr24"

    def test_crx_version_3(self, fake_config):
        import struct
        on_post_build(fake_config)
        crx = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-android.crx"
        data = crx.read_bytes()
        version = struct.unpack("<I", data[4:8])[0]
        assert version == 3

    def test_crx_contains_valid_zip(self, fake_config):
        import struct
        from io import BytesIO
        on_post_build(fake_config)
        crx = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-android.crx"
        data = crx.read_bytes()
        hs = struct.unpack("<I", data[8:12])[0]
        zip_data = data[12 + hs:]
        assert zip_data[:2] == b"PK"
        with zipfile.ZipFile(BytesIO(zip_data)) as zf:
            assert "manifest.json" in zf.namelist()

    def test_crx_manifest_no_native_messaging(self, fake_config):
        """Android CRX manifest must NOT have nativeMessaging."""
        import struct
        from io import BytesIO
        on_post_build(fake_config)
        crx = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-android.crx"
        data = crx.read_bytes()
        hs = struct.unpack("<I", data[8:12])[0]
        with zipfile.ZipFile(BytesIO(data[12 + hs:])) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert "nativeMessaging" not in manifest.get("permissions", [])

    def test_crx_manifest_has_storage(self, fake_config):
        import struct
        from io import BytesIO
        on_post_build(fake_config)
        crx = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-android.crx"
        data = crx.read_bytes()
        hs = struct.unpack("<I", data[8:12])[0]
        with zipfile.ZipFile(BytesIO(data[12 + hs:])) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert "storage" in manifest["permissions"]

    def test_crx_no_platform_dir(self, fake_config):
        """CRX should not include the platform/ SPA directory."""
        import struct
        from io import BytesIO
        on_post_build(fake_config)
        crx = Path(fake_config["site_dir"]) / "platform" / "cup-bridge-android.crx"
        data = crx.read_bytes()
        hs = struct.unpack("<I", data[8:12])[0]
        with zipfile.ZipFile(BytesIO(data[12 + hs:])) as zf:
            for name in zf.namelist():
                assert not name.startswith("platform/"), f"CRX should not contain {name}"


# ── Tests: Extension JS contract verification ────────────────────────

_EXT_SRC = _PROJECT_ROOT / "codeupipe" / "connect" / "extension"


class TestContentScriptContract:
    """Verify content-script.js has the expected structure."""

    def test_has_inject_extension_status(self):
        code = (_EXT_SRC / "content-script.js").read_text()
        assert "function injectExtensionStatus" in code

    def test_has_cup_ext_status_dom_id(self):
        code = (_EXT_SRC / "content-script.js").read_text()
        assert "cup-ext-status" in code

    def test_has_message_relay(self):
        """Content script must relay cup-request messages to service worker."""
        code = (_EXT_SRC / "content-script.js").read_text()
        assert "cup-request" in code
        assert "chrome.runtime.sendMessage" in code

    def test_does_not_inject_inline_script(self):
        """CSP fix: no inline <script> injection — that's handled by cup-bridge-api.js."""
        code = (_EXT_SRC / "content-script.js").read_text()
        assert "apiScript" not in code
        assert "document.createElement('script')" not in code

    def test_badge_probes_service_worker(self):
        code = (_EXT_SRC / "content-script.js").read_text()
        assert "badge-probe-" in code


class TestCupBridgeApiContract:
    """Verify cup-bridge-api.js defines the full window.cupBridge API."""

    def test_file_exists(self):
        assert (_EXT_SRC / "cup-bridge-api.js").is_file()

    def test_defines_window_cupbridge(self):
        code = (_EXT_SRC / "cup-bridge-api.js").read_text()
        assert "window.cupBridge" in code

    def test_fires_cup_bridge_ready_event(self):
        code = (_EXT_SRC / "cup-bridge-api.js").read_text()
        assert "cup-bridge-ready" in code

    def test_has_detected_property(self):
        code = (_EXT_SRC / "cup-bridge-api.js").read_text()
        assert "get detected()" in code
        assert "return true" in code

    def test_has_all_13_methods(self):
        """cupBridge must expose all 13 API surface methods."""
        code = (_EXT_SRC / "cup-bridge-api.js").read_text()
        expected = [
            "ping", "status", "delegate", "fetch", "provision",
            "exec", "start", "stop", "getConfig", "setConfig",
            "onStatus", "probe", "detected",
        ]
        for method in expected:
            assert method in code, f"Missing cupBridge method: {method}"

    def test_uses_post_message_relay(self):
        """API sends cup-request messages via window.postMessage."""
        code = (_EXT_SRC / "cup-bridge-api.js").read_text()
        assert "cup-request" in code
        assert "window.postMessage" in code

    def test_main_world_iife(self):
        """Must be wrapped in IIFE for MAIN world injection."""
        code = (_EXT_SRC / "cup-bridge-api.js").read_text()
        assert code.strip().startswith("/**") or code.strip().startswith("(function")
        assert "})();" in code


class TestManifestContract:
    """Verify manifest.json has correct MV3 structure."""

    def test_two_content_script_entries(self):
        manifest = json.loads((_EXT_SRC / "manifest.json").read_text())
        entries = manifest.get("content_scripts", [])
        assert len(entries) == 2

    def test_first_entry_isolated_world(self):
        manifest = json.loads((_EXT_SRC / "manifest.json").read_text())
        first = manifest["content_scripts"][0]
        assert "content-script.js" in first["js"]
        assert first.get("world", "ISOLATED") == "ISOLATED"

    def test_second_entry_main_world(self):
        manifest = json.loads((_EXT_SRC / "manifest.json").read_text())
        second = manifest["content_scripts"][1]
        assert "cup-bridge-api.js" in second["js"]
        assert second["world"] == "MAIN"

    def test_run_at_document_start(self):
        manifest = json.loads((_EXT_SRC / "manifest.json").read_text())
        for entry in manifest["content_scripts"]:
            assert entry.get("run_at") == "document_start"

    def test_matches_codeuchain_and_localhost(self):
        manifest = json.loads((_EXT_SRC / "manifest.json").read_text())
        for entry in manifest["content_scripts"]:
            matches = entry.get("matches", [])
            assert any("codeuchain.github.io" in m for m in matches)
            assert any("localhost" in m for m in matches)
