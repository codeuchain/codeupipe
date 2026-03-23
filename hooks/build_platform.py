"""MkDocs hook — build and deploy the CUP Platform site + extension zip.

Runs during ``on_post_build`` (after MkDocs has written the HTML site).
Copies the platform SPA into ``site/platform/`` and creates a downloadable
zip of the CUP Bridge Extension (desktop) and CRX (Android).

Layout produced in site/:

    site/
    └── platform/
        ├── index.html
        ├── platform.js
        ├── store.js
        ├── dashboard.js
        ├── platform.css
        ├── recipes/
        │   ├── manifest.json
        │   ├── dream-training.json
        │   └── ...
        ├── cup-bridge-extension.zip   ← desktop: unzip + Load Unpacked
        └── cup-bridge-android.crx     ← Android: sideload via Edge Dev Options
"""

import json
import shutil
import sys
import zipfile
from pathlib import Path


# ── Source paths (relative to project root) ──────────────────────────

_EXTENSION_DIR = Path("codeupipe/connect/extension")
_PLATFORM_DIR = _EXTENSION_DIR / "platform"
_RECIPES_DIR = _EXTENSION_DIR / "recipes"

# Files that make up the platform SPA
_PLATFORM_FILES = [
    "index.html",
    "platform.js",
    "store.js",
    "dashboard.js",
    "platform.css",
]

# Extension files to include in the zip
_EXTENSION_FILES = [
    "manifest.json",
    "service-worker.js",
    "content-script.js",
    "cup-bridge-api.js",
    "popup.html",
]


def on_post_build(config, **kwargs):
    """Copy platform SPA + build extension zip into site/platform/."""
    project_root = Path(config["config_file_path"]).parent
    site_dir = Path(config["site_dir"])

    platform_src = project_root / _PLATFORM_DIR
    recipes_src = project_root / _RECIPES_DIR
    extension_src = project_root / _EXTENSION_DIR

    platform_dest = site_dir / "platform"
    platform_dest.mkdir(parents=True, exist_ok=True)

    # ── 1. Copy platform SPA files ───────────────────────────────

    for name in _PLATFORM_FILES:
        src = platform_src / name
        if src.exists():
            shutil.copy2(str(src), str(platform_dest / name))
            print(f"  [platform] copied {name}")
        else:
            print(f"  [platform] WARNING: {name} not found")

    # ── 2. Copy recipes (resolve symlink) ────────────────────────

    recipes_dest = platform_dest / "recipes"
    if recipes_dest.exists():
        shutil.rmtree(str(recipes_dest))
    recipes_dest.mkdir(parents=True, exist_ok=True)

    if recipes_src.exists():
        for recipe_file in sorted(recipes_src.iterdir()):
            if recipe_file.is_file():
                shutil.copy2(str(recipe_file), str(recipes_dest / recipe_file.name))
                print(f"  [platform] recipe: {recipe_file.name}")
    else:
        print("  [platform] WARNING: recipes/ not found")

    # ── 3. Build extension zip ───────────────────────────────────

    zip_path = platform_dest / "cup-bridge-extension.zip"
    _build_extension_zip(extension_src, zip_path)
    print(f"  [platform] extension zip: {zip_path.name}")

    # ── 4. Build Android CRX ─────────────────────────────────────

    crx_path = platform_dest / "cup-bridge-android.crx"
    android_manifest = extension_src / "manifest.android.json"
    _build_android_crx(extension_src, android_manifest, crx_path, project_root)
    print(f"  [platform] android crx: {crx_path.name}")


def _build_extension_zip(extension_src: Path, zip_path: Path):
    """Create a loadable Chrome extension zip.

    - Copies manifest.json, fixing icon paths if needed
    - Includes service-worker.js, content-script.js, popup.html
    - Includes icon files in icons/ directory
    - Includes recipes/ directory
    - Includes native/ directory (for optional NM host setup)
    """
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        # manifest.json — fix icon paths (source has icon-N.png at root,
        # manifest references icons/icon-N.png)
        manifest_path = extension_src / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        # Core extension files
        for name in _EXTENSION_FILES[1:]:  # skip manifest (already added)
            src = extension_src / name
            if src.exists():
                zf.write(str(src), name)

        # Icons — source files are in icons/ subdirectory
        icons_dir = extension_src / "icons"
        if icons_dir.exists():
            for icon_file in sorted(icons_dir.glob("icon-*.png")):
                zf.write(str(icon_file), f"icons/{icon_file.name}")

        # Recipes
        recipes_dir = extension_src / "recipes"
        if recipes_dir.exists():
            for recipe_file in sorted(recipes_dir.iterdir()):
                if recipe_file.is_file():
                    zf.write(str(recipe_file), f"recipes/{recipe_file.name}")

        # Native host files
        native_dir = extension_src / "native"
        if native_dir.exists():
            for native_file in sorted(native_dir.iterdir()):
                if native_file.is_file():
                    zf.write(str(native_file), f"native/{native_file.name}")


def _build_android_crx(
    extension_src: Path,
    android_manifest: Path,
    crx_path: Path,
    project_root: Path,
):
    """Build a CRX3 file for Android sideloading.

    Uses the build_crx module from the extension directory itself.
    The Android manifest strips ``nativeMessaging`` (unavailable on
    Android) so the extension installs cleanly and falls back to the
    WASM tier automatically.
    """
    if not android_manifest.exists():
        print("  [platform] WARNING: manifest.android.json not found — skipping CRX")
        return

    # Import build_crx from the extension directory (stdlib-only, no deps)
    build_crx_path = extension_src / "build_crx.py"
    if not build_crx_path.exists():
        print("  [platform] WARNING: build_crx.py not found — skipping CRX")
        return

    import importlib.util
    spec = importlib.util.spec_from_file_location("build_crx", str(build_crx_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    try:
        crx_bytes = mod.build_crx(
            extension_src,
            manifest_override=android_manifest,
        )
        crx_path.write_bytes(crx_bytes)
        size_kb = len(crx_bytes) / 1024
        print(f"  [platform] android CRX: {size_kb:.1f} KB")
    except Exception as exc:
        print(f"  [platform] WARNING: CRX build failed: {exc}")
