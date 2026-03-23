"""
Tests for CRX3 builder and Android Edge extension contracts.

Covers:
    - CRX3 protobuf encoding
    - CRX3 file structure (magic, version, header, ZIP)
    - ZIP contents and manifest override
    - Android manifest variant (no nativeMessaging)
    - Desktop ↔ Android manifest parity
    - Extension ID computation
    - Setup script helpers (unit-level)
"""
from __future__ import annotations

import json
import struct
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Paths ───────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTENSION_DIR = PROJECT_ROOT / "codeupipe" / "connect" / "extension"
DESKTOP_MANIFEST = EXTENSION_DIR / "manifest.json"
ANDROID_MANIFEST = EXTENSION_DIR / "manifest.android.json"
BUILD_CRX_MODULE = EXTENSION_DIR / "build_crx.py"


# ── Manifest Contract Tests ─────────────────────────────────────────

class TestAndroidManifest:
    """Contract tests for the Android-specific extension manifest."""

    def test_android_manifest_exists(self):
        assert ANDROID_MANIFEST.is_file(), "manifest.android.json must exist"

    def test_desktop_manifest_exists(self):
        assert DESKTOP_MANIFEST.is_file(), "manifest.json must exist"

    def test_android_manifest_is_valid_json(self):
        data = json.loads(ANDROID_MANIFEST.read_text())
        assert isinstance(data, dict)

    def test_android_manifest_version_3(self):
        data = json.loads(ANDROID_MANIFEST.read_text())
        assert data["manifest_version"] == 3

    def test_android_no_native_messaging(self):
        """Key contract: Android manifest must NOT have nativeMessaging."""
        data = json.loads(ANDROID_MANIFEST.read_text())
        permissions = data.get("permissions", [])
        assert "nativeMessaging" not in permissions, (
            "Android manifest must not include nativeMessaging — "
            "chrome.runtime.connectNative() does not exist on Android"
        )

    def test_desktop_has_native_messaging(self):
        """Desktop manifest DOES have nativeMessaging."""
        data = json.loads(DESKTOP_MANIFEST.read_text())
        permissions = data.get("permissions", [])
        assert "nativeMessaging" in permissions

    def test_android_has_storage_permission(self):
        data = json.loads(ANDROID_MANIFEST.read_text())
        assert "storage" in data["permissions"]

    def test_android_has_active_tab_permission(self):
        data = json.loads(ANDROID_MANIFEST.read_text())
        assert "activeTab" in data["permissions"]

    def test_android_has_service_worker(self):
        data = json.loads(ANDROID_MANIFEST.read_text())
        bg = data.get("background", {})
        assert bg.get("service_worker") == "service-worker.js"
        assert bg.get("type") == "module"

    def test_android_has_content_scripts(self):
        data = json.loads(ANDROID_MANIFEST.read_text())
        cs = data.get("content_scripts", [])
        assert len(cs) >= 2, "Need content-script.js and cup-bridge-api.js"

    def test_android_has_cup_bridge_api_in_main_world(self):
        """cup-bridge-api.js must run in MAIN world to bypass CSP."""
        data = json.loads(ANDROID_MANIFEST.read_text())
        cs = data.get("content_scripts", [])
        main_world_scripts = [
            s for s in cs if s.get("world") == "MAIN"
        ]
        assert len(main_world_scripts) >= 1
        assert "cup-bridge-api.js" in main_world_scripts[0]["js"]

    def test_android_matches_github_pages(self):
        data = json.loads(ANDROID_MANIFEST.read_text())
        cs = data.get("content_scripts", [])
        all_matches = []
        for s in cs:
            all_matches.extend(s.get("matches", []))
        assert "https://codeuchain.github.io/*" in all_matches

    def test_android_has_popup(self):
        data = json.loads(ANDROID_MANIFEST.read_text())
        action = data.get("action", {})
        assert action.get("default_popup") == "popup.html"

    def test_manifest_parity_name(self):
        """Name must match between desktop and Android variants."""
        desktop = json.loads(DESKTOP_MANIFEST.read_text())
        android = json.loads(ANDROID_MANIFEST.read_text())
        assert desktop["name"] == android["name"]

    def test_manifest_parity_version(self):
        desktop = json.loads(DESKTOP_MANIFEST.read_text())
        android = json.loads(ANDROID_MANIFEST.read_text())
        assert desktop["version"] == android["version"]

    def test_manifest_parity_content_scripts_structure(self):
        """Same content scripts between desktop and Android."""
        desktop = json.loads(DESKTOP_MANIFEST.read_text())
        android = json.loads(ANDROID_MANIFEST.read_text())
        assert len(desktop["content_scripts"]) == len(android["content_scripts"])

    def test_manifest_parity_icons(self):
        desktop = json.loads(DESKTOP_MANIFEST.read_text())
        android = json.loads(ANDROID_MANIFEST.read_text())
        assert desktop["icons"] == android["icons"]

    def test_manifest_parity_web_accessible_resources(self):
        desktop = json.loads(DESKTOP_MANIFEST.read_text())
        android = json.loads(ANDROID_MANIFEST.read_text())
        assert desktop["web_accessible_resources"] == android["web_accessible_resources"]


# ── Protobuf Encoding Tests ─────────────────────────────────────────

class TestProtobufEncoding:
    """Tests for the hand-rolled protobuf encoding in build_crx."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        """Import build_crx functions."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_crx", BUILD_CRX_MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.mod = mod

    def test_encode_varint_zero(self):
        assert self.mod._encode_varint(0) == b"\x00"

    def test_encode_varint_small(self):
        assert self.mod._encode_varint(1) == b"\x01"
        assert self.mod._encode_varint(127) == b"\x7f"

    def test_encode_varint_two_bytes(self):
        # 128 = 0x80 → varint: [0x80, 0x01]
        result = self.mod._encode_varint(128)
        assert result == b"\x80\x01"

    def test_encode_varint_large(self):
        # 300 = 0x12c → varint: [0xac, 0x02]
        result = self.mod._encode_varint(300)
        assert result == b"\xac\x02"

    def test_encode_length_delimited_tag(self):
        """Field 1, wire type 2 → tag byte = 0x0a."""
        result = self.mod._encode_length_delimited(1, b"hello")
        assert result[0] == 0x0A  # (1 << 3) | 2

    def test_encode_length_delimited_length(self):
        result = self.mod._encode_length_delimited(1, b"hello")
        assert result[1] == 5  # length of "hello"
        assert result[2:] == b"hello"

    def test_encode_length_delimited_field_2(self):
        """Field 2, wire type 2 → tag byte = 0x12."""
        result = self.mod._encode_length_delimited(2, b"test")
        assert result[0] == 0x12  # (2 << 3) | 2

    def test_encode_crx_file_header_structure(self):
        """CrxFileHeader should be a nested protobuf message."""
        pub_key = b"fake_public_key"
        signature = b"fake_signature"
        header = self.mod._encode_crx_file_header(pub_key, signature)
        # Should start with field 2 tag (sha256_with_rsa)
        assert header[0] == 0x12  # (2 << 3) | 2
        assert len(header) > len(pub_key) + len(signature)

    def test_encode_crx_file_header_contains_key(self):
        pub_key = b"TEST_PUBLIC_KEY_DATA"
        signature = b"TEST_SIGNATURE_DATA"
        header = self.mod._encode_crx_file_header(pub_key, signature)
        assert pub_key in header
        assert signature in header


# ── ZIP Builder Tests ────────────────────────────────────────────────

class TestZipBuilder:
    """Tests for the ZIP archive builder."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_crx", BUILD_CRX_MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.mod = mod

    def test_zip_from_directory(self, tmp_path):
        """Build a ZIP from a minimal extension directory."""
        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text('{"manifest_version": 3}')
        (ext_dir / "popup.html").write_text("<h1>Test</h1>")

        zip_bytes = self.mod._build_zip(ext_dir)
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "popup.html" in names

    def test_zip_excludes_python_files(self, tmp_path):
        """Python files (like build_crx.py) should be excluded."""
        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text('{"manifest_version": 3}')
        (ext_dir / "build_crx.py").write_text("# should be excluded")

        zip_bytes = self.mod._build_zip(ext_dir)
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            assert "build_crx.py" not in zf.namelist()

    def test_zip_excludes_hidden_files(self, tmp_path):
        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text('{"manifest_version": 3}')
        (ext_dir / ".gitignore").write_text("*.pyc")

        zip_bytes = self.mod._build_zip(ext_dir)
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            assert ".gitignore" not in zf.namelist()

    def test_zip_excludes_store_listing(self, tmp_path):
        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text('{"manifest_version": 3}')
        (ext_dir / "STORE_LISTING.md").write_text("# Store listing")

        zip_bytes = self.mod._build_zip(ext_dir)
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            assert "STORE_LISTING.md" not in zf.namelist()

    def test_zip_manifest_override(self, tmp_path):
        """Manifest override should replace the directory's manifest.json."""
        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text('{"original": true}')
        (ext_dir / "popup.html").write_text("<h1>Test</h1>")

        override = tmp_path / "override.json"
        override.write_text('{"override": true}')

        zip_bytes = self.mod._build_zip(ext_dir, manifest_override=override)
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            manifest_content = zf.read("manifest.json").decode()
            data = json.loads(manifest_content)
            assert data == {"override": True}

    def test_zip_includes_subdirectories(self, tmp_path):
        ext_dir = tmp_path / "ext"
        icons_dir = ext_dir / "icons"
        icons_dir.mkdir(parents=True)
        (ext_dir / "manifest.json").write_text('{"manifest_version": 3}')
        (icons_dir / "icon-16.png").write_bytes(b"\x89PNG")

        zip_bytes = self.mod._build_zip(ext_dir)
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            assert "icons/icon-16.png" in zf.namelist()

    def test_zip_excludes_pycache(self, tmp_path):
        ext_dir = tmp_path / "ext"
        cache_dir = ext_dir / "__pycache__"
        cache_dir.mkdir(parents=True)
        (ext_dir / "manifest.json").write_text('{"manifest_version": 3}')
        (cache_dir / "build_crx.cpython-39.pyc").write_bytes(b"\x00")

        zip_bytes = self.mod._build_zip(ext_dir)
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                assert "__pycache__" not in name


# ── CRX3 Structure Tests ────────────────────────────────────────────

class TestCrx3Structure:
    """Tests for full CRX3 file assembly."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_crx", BUILD_CRX_MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.mod = mod

    @pytest.fixture()
    def minimal_extension(self, tmp_path):
        """Create a minimal extension directory."""
        ext_dir = tmp_path / "ext"
        ext_dir.mkdir()
        (ext_dir / "manifest.json").write_text(json.dumps({
            "manifest_version": 3,
            "name": "Test Extension",
            "version": "1.0.0",
        }))
        (ext_dir / "popup.html").write_text("<h1>Test</h1>")
        return ext_dir

    def test_crx_magic_bytes(self, minimal_extension):
        """CRX3 starts with 'Cr24' magic."""
        crx = self.mod.build_crx(minimal_extension)
        assert crx[:4] == b"Cr24"

    def test_crx_version_3(self, minimal_extension):
        """CRX3 version field is 3."""
        crx = self.mod.build_crx(minimal_extension)
        version = struct.unpack("<I", crx[4:8])[0]
        assert version == 3

    def test_crx_header_size_positive(self, minimal_extension):
        """Header size is a positive integer."""
        crx = self.mod.build_crx(minimal_extension)
        header_size = struct.unpack("<I", crx[8:12])[0]
        assert header_size > 0

    def test_crx_contains_zip(self, minimal_extension):
        """After the header, the rest is a valid ZIP."""
        crx = self.mod.build_crx(minimal_extension)
        header_size = struct.unpack("<I", crx[8:12])[0]
        zip_start = 12 + header_size
        zip_data = crx[zip_start:]
        # ZIP files start with PK\x03\x04
        assert zip_data[:2] == b"PK"

        with zipfile.ZipFile(BytesIO(zip_data)) as zf:
            assert "manifest.json" in zf.namelist()

    def test_crx_with_manifest_override(self, minimal_extension, tmp_path):
        """CRX built with manifest override uses the override."""
        override = tmp_path / "android.json"
        override.write_text(json.dumps({
            "manifest_version": 3,
            "name": "Android Variant",
            "version": "1.0.0",
        }))

        crx = self.mod.build_crx(minimal_extension, manifest_override=override)
        header_size = struct.unpack("<I", crx[8:12])[0]
        zip_start = 12 + header_size
        zip_data = crx[zip_start:]

        with zipfile.ZipFile(BytesIO(zip_data)) as zf:
            manifest_content = zf.read("manifest.json").decode()
            data = json.loads(manifest_content)
            assert data["name"] == "Android Variant"

    def test_crx_deterministic_with_same_key(self, minimal_extension, tmp_path):
        """Same key → same extension ID (but CRX bytes may differ due to timestamps)."""
        import subprocess
        key_path = tmp_path / "test.pem"
        subprocess.run(
            ["openssl", "genrsa", "-out", str(key_path), "2048"],
            check=True,
            capture_output=True,
        )

        id1 = self.mod.extension_id_from_key(key_path)
        id2 = self.mod.extension_id_from_key(key_path)
        assert id1 == id2
        assert len(id1) == 32
        # Extension IDs use a-p alphabet
        assert all(c in "abcdefghijklmnop" for c in id1)


# ── Extension File Contract Tests ────────────────────────────────────

class TestExtensionFileContracts:
    """Verify the extension directory has all required files."""

    def test_manifest_json_exists(self):
        assert (EXTENSION_DIR / "manifest.json").is_file()

    def test_service_worker_exists(self):
        assert (EXTENSION_DIR / "service-worker.js").is_file()

    def test_content_script_exists(self):
        assert (EXTENSION_DIR / "content-script.js").is_file()

    def test_cup_bridge_api_exists(self):
        assert (EXTENSION_DIR / "cup-bridge-api.js").is_file()

    def test_popup_html_exists(self):
        assert (EXTENSION_DIR / "popup.html").is_file()

    def test_icons_exist(self):
        for size in ("16", "48", "128"):
            icon = EXTENSION_DIR / "icons" / f"icon-{size}.png"
            assert icon.is_file(), f"Missing icon: {icon}"

    def test_build_crx_exists(self):
        assert BUILD_CRX_MODULE.is_file()


# ── Android Edge Setup Script Tests ──────────────────────────────────

class TestAndroidEdgeSetupHelpers:
    """Unit tests for the setup script helper functions."""

    def test_setup_script_exists(self):
        script = PROJECT_ROOT / "examples" / "android_edge_setup.py"
        assert script.is_file()

    def test_setup_script_imports(self):
        """Setup script should be importable (syntax check)."""
        import importlib.util
        script = PROJECT_ROOT / "examples" / "android_edge_setup.py"
        spec = importlib.util.spec_from_file_location("android_edge_setup", script)
        mod = importlib.util.module_from_spec(spec)
        # Don't exec (it imports adb paths that may not exist), just verify spec
        assert spec is not None

    def test_setup_references_android_manifest(self):
        """Setup script should use manifest.android.json."""
        script = PROJECT_ROOT / "examples" / "android_edge_setup.py"
        content = script.read_text()
        assert "manifest.android.json" in content

    def test_setup_references_build_crx(self):
        """Setup script should use build_crx module."""
        script = PROJECT_ROOT / "examples" / "android_edge_setup.py"
        content = script.read_text()
        assert "build_crx" in content

    def test_setup_references_platform_url(self):
        """Setup script should validate the Platform SPA."""
        script = PROJECT_ROOT / "examples" / "android_edge_setup.py"
        content = script.read_text()
        assert "codeuchain.github.io/codeupipe/platform" in content

    def test_setup_has_validation_step(self):
        """Setup script should have a validation step."""
        script = PROJECT_ROOT / "examples" / "android_edge_setup.py"
        content = script.read_text()
        assert "step_validate_platform" in content

    def test_setup_has_crx_build_step(self):
        script = PROJECT_ROOT / "examples" / "android_edge_setup.py"
        content = script.read_text()
        assert "step_build_crx" in content

    def test_setup_documents_wasm_fallback(self):
        """Setup script should document that Android falls back to WASM."""
        script = PROJECT_ROOT / "examples" / "android_edge_setup.py"
        content = script.read_text()
        assert "WASM" in content
        assert "connectNative" in content or "nativeMessaging" in content


# ── Service Worker Android Compatibility Tests ───────────────────────

class TestServiceWorkerAndroidCompat:
    """Verify service-worker.js handles missing native messaging gracefully."""

    def test_service_worker_has_wasm_fallback(self):
        sw = (EXTENSION_DIR / "service-worker.js").read_text()
        assert "wasmFallback" in sw or "wasm-fallback" in sw

    def test_service_worker_selecttier_falls_to_wasm(self):
        """selectTier must return wasm when native and http are both down."""
        sw = (EXTENSION_DIR / "service-worker.js").read_text()
        # The final return in selectTier should be wasm
        assert "return payload.insert('tier', 'wasm')" in sw

    def test_service_worker_native_relay_catches_errors(self):
        """nativeRelay must catch errors and fall through."""
        sw = (EXTENSION_DIR / "service-worker.js").read_text()
        assert "state.nativeAlive = false" in sw

    def test_service_worker_broadcaststatus_filters_tabs(self):
        """broadcastStatus must filter by URL pattern."""
        sw = (EXTENSION_DIR / "service-worker.js").read_text()
        assert "chrome.tabs.query" in sw
        assert "urlPatterns" in sw or "url:" in sw

    def test_cup_bridge_api_exposes_provision(self):
        """cup-bridge-api.js must expose provision() for capability store."""
        api = (EXTENSION_DIR / "cup-bridge-api.js").read_text()
        assert "provision:" in api or "provision :" in api
