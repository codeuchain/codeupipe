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
