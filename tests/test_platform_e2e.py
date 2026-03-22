"""
E2E tests for the CUP Platform site.

Three test tiers:
    1. TestPlatformServing — verify static files serve correctly (stdlib only)
    2. TestPlatformPlaywright — Playwright E2E: load site, verify DOM, JS init,
       recipe loading, interactive elements
    3. TestPlatformCupBrowser — dogfood: use CUP Browser Filters + PlaywrightBridge
       to validate the platform site through CUP pipelines

All tests self-host: a background HTTP server starts in a fixture and
shuts down after the test session.

URL: http://127.0.0.1:{PORT}/
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import threading
import time
from pathlib import Path
from urllib.request import urlopen
from unittest.mock import MagicMock

import pytest

# ── Locate platform directory ────────────────────────────────────────

PLATFORM_DIR = (
    Path(__file__).resolve().parent.parent
    / "codeupipe" / "connect" / "extension" / "platform"
)
RECIPES_DIR = PLATFORM_DIR.parent / "recipes"

# ── Helper: find a free port ─────────────────────────────────────────

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── Fixture: self-hosted platform server ─────────────────────────────

class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that suppresses request logging."""
    def log_message(self, fmt, *args):
        pass  # silence


@pytest.fixture(scope="module")
def platform_url():
    """Start an HTTP server serving the platform directory.

    Returns the base URL (e.g. http://127.0.0.1:8199).
    The server runs in a daemon thread and shuts down after the module.
    """
    port = _free_port()

    handler = lambda *a, **kw: _SilentHandler(
        *a, directory=str(PLATFORM_DIR), **kw
    )
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}"

    # Wait for server to be ready
    for _ in range(20):
        try:
            urlopen(f"{url}/platform.js", timeout=1)
            break
        except Exception:
            time.sleep(0.1)

    yield url

    server.shutdown()


# ═══════════════════════════════════════════════════════════════════════
# TIER 1 — Static file serving (stdlib only)
# ═══════════════════════════════════════════════════════════════════════


class TestPlatformServing:
    """Verify all platform files are served correctly."""

    def test_index_html_served(self, platform_url):
        resp = urlopen(f"{platform_url}/")
        html = resp.read().decode()
        assert "CUP Platform" in html
        assert "cup-header" in html

    def test_platform_js_served(self, platform_url):
        resp = urlopen(f"{platform_url}/platform.js")
        js = resp.read().decode()
        assert "CupPlatform" in js
        assert "Payload" in js

    def test_store_js_served(self, platform_url):
        resp = urlopen(f"{platform_url}/store.js")
        js = resp.read().decode()
        assert "CupStore" in js

    def test_dashboard_js_served(self, platform_url):
        resp = urlopen(f"{platform_url}/dashboard.js")
        js = resp.read().decode()
        assert "CupDashboard" in js

    def test_platform_css_served(self, platform_url):
        resp = urlopen(f"{platform_url}/platform.css")
        css = resp.read().decode()
        assert "--bg" in css
        assert "cup-store-card" in css

    def test_recipes_manifest_served(self, platform_url):
        resp = urlopen(f"{platform_url}/recipes/manifest.json")
        data = json.loads(resp.read())
        assert "capabilities" in data
        assert len(data["capabilities"]) >= 5

    def test_dream_training_recipe_served(self, platform_url):
        resp = urlopen(f"{platform_url}/recipes/dream-training.json")
        data = json.loads(resp.read())
        assert data["id"] == "dream-training"
        assert "steps" in data

    def test_onnx_recipe_served(self, platform_url):
        resp = urlopen(f"{platform_url}/recipes/onnx-inference.json")
        data = json.loads(resp.read())
        assert data["id"] == "onnx-inference"
        assert data["tier"] == "wasm"

    def test_all_recipes_loadable(self, platform_url):
        resp = urlopen(f"{platform_url}/recipes/manifest.json")
        manifest = json.loads(resp.read())
        for cap in manifest["capabilities"]:
            recipe_resp = urlopen(
                f"{platform_url}/recipes/{cap['recipe']}"
            )
            recipe = json.loads(recipe_resp.read())
            assert recipe["id"] == cap["id"]


# ═══════════════════════════════════════════════════════════════════════
# TIER 2 — Playwright E2E (real browser, full DOM/JS validation)
# ═══════════════════════════════════════════════════════════════════════

_has_playwright = False
try:
    from playwright.sync_api import sync_playwright
    _has_playwright = True
except ImportError:
    pass

pw = pytest.mark.skipif(not _has_playwright, reason="playwright not installed")


@pytest.fixture(scope="module")
def browser_page(platform_url):
    """Launch Chromium, navigate to platform, yield page, cleanup."""
    if not _has_playwright:
        pytest.skip("playwright not installed")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(platform_url)
        # Wait for init script to complete AND recipes to load
        page.wait_for_function(
            "typeof CupPlatform !== 'undefined' && CupPlatform.recipes !== null",
            timeout=10000,
        )
        yield page
        context.close()
        browser.close()


@pw
class TestPlatformPlaywright:
    """Full browser E2E — load site, verify DOM, JS init, recipes, interactivity."""

    # ── Page Structure ──────────────────────────────────────────────

    def test_page_title(self, browser_page):
        assert "CUP Platform" in browser_page.title()

    def test_header_visible(self, browser_page):
        header = browser_page.locator(".cup-header")
        assert header.is_visible()
        assert "CUP Platform" in header.inner_text()

    def test_header_tier_badge_exists(self, browser_page):
        badge = browser_page.locator("#header-tier")
        assert badge.is_visible()
        # Without extension, tier should be 'no-extension' or similar
        text = badge.inner_text()
        assert len(text) > 0

    # ── Dashboard Section ───────────────────────────────────────────

    def test_dashboard_grid_exists(self, browser_page):
        grid = browser_page.locator(".cup-dash-grid")
        assert grid.is_visible()

    def test_dashboard_cards_count(self, browser_page):
        cards = browser_page.locator(".cup-dash-card")
        assert cards.count() == 6  # Extension, Tier, Device, Native, HTTP, Capabilities

    def test_extension_status_shows_not_detected(self, browser_page):
        # Dashboard should have refreshed by now (recipes loaded = init done)
        ext = browser_page.locator("#dash-extension")
        # Wait for dashboard to update from "Checking…"
        browser_page.wait_for_function(
            "document.getElementById('dash-extension').textContent !== 'Checking…'",
            timeout=5000,
        )
        text = ext.inner_text()
        assert "Not" in text or "❌" in text

    def test_tier_shows_no_extension(self, browser_page):
        tier = browser_page.locator("#dash-tier")
        text = tier.inner_text()
        # Without extension, should show some disconnect state
        assert len(text) > 0

    def test_probe_button_exists(self, browser_page):
        btn = browser_page.locator("#btn-probe")
        assert btn.is_visible()
        assert "probe" in btn.inner_text().lower() or "🔄" in btn.inner_text()

    # ── Capability Store ────────────────────────────────────────────

    def test_store_section_exists(self, browser_page):
        store = browser_page.locator("#cup-store")
        # Wait for store to be populated with at least one card
        browser_page.wait_for_selector(".cup-store-card", timeout=5000)
        assert store.count() >= 1

    def test_store_renders_capability_cards(self, browser_page):
        browser_page.wait_for_selector(".cup-store-card", timeout=5000)
        cards = browser_page.locator(".cup-store-card")
        assert cards.count() >= 5  # 5 recipes in manifest

    def test_store_cards_have_names(self, browser_page):
        names = browser_page.locator(".cup-store-name")
        for i in range(names.count()):
            text = names.nth(i).inner_text()
            assert len(text) > 0

    def test_store_cards_have_tier_badges(self, browser_page):
        badges = browser_page.locator(".cup-store-tier .tier-badge")
        assert badges.count() >= 5

    def test_store_cards_have_toggles(self, browser_page):
        toggles = browser_page.locator(".cup-store-toggle input[type='checkbox']")
        assert toggles.count() >= 5
        # All should be unchecked initially
        for i in range(toggles.count()):
            assert not toggles.nth(i).is_checked()

    def test_store_has_dream_training(self, browser_page):
        dream = browser_page.locator(".cup-store-card[data-id='dream-training']")
        assert dream.count() == 1
        assert "Dream" in dream.inner_text()

    def test_store_has_onnx_inference(self, browser_page):
        onnx = browser_page.locator(".cup-store-card[data-id='onnx-inference']")
        assert onnx.count() == 1
        assert "ONNX" in onnx.inner_text()

    # ── JavaScript Global Objects ───────────────────────────────────

    def test_cup_platform_defined(self, browser_page):
        result = browser_page.evaluate("typeof CupPlatform")
        assert result == "object"

    def test_cup_store_defined(self, browser_page):
        result = browser_page.evaluate("typeof CupStore")
        assert result == "object"

    def test_cup_dashboard_defined(self, browser_page):
        result = browser_page.evaluate("typeof CupDashboard")
        assert result == "object"

    def test_cup_platform_payload_class(self, browser_page):
        result = browser_page.evaluate(
            "typeof CupPlatform.Payload === 'function'"
        )
        assert result is True

    def test_cup_platform_tier(self, browser_page):
        tier = browser_page.evaluate("CupPlatform.tier")
        assert isinstance(tier, str)
        assert len(tier) > 0

    def test_cup_platform_detected_false_without_extension(self, browser_page):
        detected = browser_page.evaluate("CupPlatform.detected")
        assert detected is False

    def test_cup_platform_recipes_loaded(self, browser_page):
        recipes = browser_page.evaluate("CupPlatform.recipes")
        assert recipes is not None
        assert "capabilities" in recipes
        assert len(recipes["capabilities"]) >= 5

    # ── CUP Payload in-browser ──────────────────────────────────────

    def test_payload_immutable_insert(self, browser_page):
        result = browser_page.evaluate("""
            (() => {
                const p1 = new CupPlatform.Payload({a: 1});
                const p2 = p1.insert('b', 2);
                return {
                    p1_has_b: p1.get('b', null),
                    p2_has_b: p2.get('b'),
                    p1_has_a: p1.get('a'),
                    p2_has_a: p2.get('a'),
                };
            })()
        """)
        assert result["p1_has_b"] is None  # immutable — p1 unchanged
        assert result["p2_has_b"] == 2
        assert result["p1_has_a"] == 1
        assert result["p2_has_a"] == 1

    def test_payload_get_default(self, browser_page):
        result = browser_page.evaluate("""
            new CupPlatform.Payload({}).get('missing', 'fallback')
        """)
        assert result == "fallback"

    # ── Install Section ─────────────────────────────────────────────

    def test_install_section_visible_without_extension(self, browser_page):
        section = browser_page.locator("#install-section")
        assert section.is_visible()

    def test_install_section_has_download_link(self, browser_page):
        link = browser_page.locator("#install-section a[download]")
        assert link.count() >= 1

    # ── Footer ──────────────────────────────────────────────────────

    def test_footer_exists(self, browser_page):
        footer = browser_page.locator(".cup-footer")
        assert footer.is_visible()
        assert "codeupipe" in footer.inner_text().lower()

    # ── Interaction: Toggle triggers extension prompt ────────────────

    def test_toggle_without_extension_shows_prompt(self, browser_page):
        # Click the first toggle's visible slider label (not the hidden input)
        browser_page.wait_for_selector(".cup-store-card", timeout=5000)
        toggle = browser_page.locator(
            ".cup-store-toggle input[type='checkbox']"
        ).first
        # The input is visually hidden (opacity:0, w:0, h:0), use dispatchEvent
        toggle.dispatch_event("click")

        # Should show extension prompt overlay
        browser_page.wait_for_selector("#cup-ext-prompt", timeout=2000)
        prompt = browser_page.locator("#cup-ext-prompt")
        assert prompt.is_visible()
        assert "Extension" in prompt.inner_text()

        # Close the prompt
        close_btn = prompt.locator("button")
        close_btn.click()
        browser_page.wait_for_function(
            "document.getElementById('cup-ext-prompt').style.display === 'none'",
            timeout=2000,
        )


# ═══════════════════════════════════════════════════════════════════════
# TIER 3 — CUP Browser Filters (dogfooding cup browser)
#
# Because pytest-playwright owns the event loop, we can't call
# sync_playwright() again in the same process.  Instead we shell out
# to a fresh Python process for each test.
# ═══════════════════════════════════════════════════════════════════════

import subprocess
import sys
import textwrap


def _run_browser_test(script: str, timeout: int = 60):
    """Run a Python script in a subprocess.  Asserts exit code 0."""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Subprocess failed (exit {result.returncode}):\n"
            f"STDOUT: {result.stdout[-500:]}\n"
            f"STDERR: {result.stderr[-500:]}"
        )


@pw
class TestPlatformCupBrowser:
    """Dogfood: use CUP Browser Filters with PlaywrightBridge to validate
    the platform site.  Each test runs in a subprocess to avoid event loop
    conflicts with pytest-playwright.

    Uses direct filter.call() chains (not Pipeline.run()) because
    Playwright sync API owns the event loop and Pipeline.run() is async.
    This is the authentic Filter dogfood pattern.
    """

    def test_open_and_eval_via_cup_filters(self, platform_url):
        _run_browser_test(f"""
            import json
            from codeupipe import Payload
            from codeupipe.browser.playwright_bridge import PlaywrightBridge
            from codeupipe.browser import BrowserOpen, BrowserEval

            with PlaywrightBridge(headless=True) as bridge:
                p = Payload()
                p = BrowserOpen(bridge=bridge, url="{platform_url}").call(p)
                p = BrowserEval(
                    bridge=bridge,
                    expression="JSON.stringify({{tier: CupPlatform.tier, detected: CupPlatform.detected}})",
                ).call(p)

                assert p.get("browser_ok") is True, f"browser_ok={{p.get('browser_ok')}}"
                data = json.loads(p.get("browser_eval", "{{}}"))
                assert data["detected"] is False
                assert isinstance(data["tier"], str)
                print("PASS: open_and_eval")
        """)

    def test_snapshot_via_cup_filter(self, platform_url):
        _run_browser_test(f"""
            from codeupipe import Payload
            from codeupipe.browser.playwright_bridge import PlaywrightBridge
            from codeupipe.browser import BrowserOpen, BrowserSnapshot

            with PlaywrightBridge(headless=True) as bridge:
                p = Payload()
                p = BrowserOpen(bridge=bridge, url="{platform_url}").call(p)
                p = BrowserSnapshot(bridge=bridge).call(p)

                assert p.get("browser_ok") is True
                snapshot = p.get("browser_snapshot", "")
                assert len(snapshot) > 20, f"snapshot too short: {{len(snapshot)}}"
                print("PASS: snapshot")
        """)

    def test_screenshot_via_cup_filter(self, platform_url, tmp_path):
        ss_path = str(tmp_path / "platform.png")
        _run_browser_test(f"""
            from pathlib import Path
            from codeupipe import Payload
            from codeupipe.browser.playwright_bridge import PlaywrightBridge
            from codeupipe.browser import BrowserOpen, BrowserScreenshot

            with PlaywrightBridge(headless=True) as bridge:
                p = Payload()
                p = BrowserOpen(bridge=bridge, url="{platform_url}").call(p)
                p = BrowserScreenshot(bridge=bridge, path="{ss_path}").call(p)

                assert p.get("browser_ok") is True
                assert Path("{ss_path}").exists()
                assert Path("{ss_path}").stat().st_size > 1000
                print("PASS: screenshot")
        """)

    def test_get_title_via_cup_filter(self, platform_url):
        _run_browser_test(f"""
            from codeupipe import Payload
            from codeupipe.browser.playwright_bridge import PlaywrightBridge
            from codeupipe.browser import BrowserOpen, BrowserGet

            with PlaywrightBridge(headless=True) as bridge:
                p = Payload({{"browser_get_what": "title"}})
                p = BrowserOpen(bridge=bridge, url="{platform_url}").call(p)
                p = BrowserGet(bridge=bridge).call(p)

                assert p.get("browser_ok") is True
                title = p.get("browser_get_result", "")
                assert "CUP Platform" in title, f"title={{title}}"
                print("PASS: get_title")
        """)

    def test_eval_recipe_count(self, platform_url):
        _run_browser_test(f"""
            from codeupipe import Payload
            from codeupipe.browser.playwright_bridge import PlaywrightBridge
            from codeupipe.browser import BrowserOpen, BrowserEval

            with PlaywrightBridge(headless=True) as bridge:
                p = Payload()
                p = BrowserOpen(bridge=bridge, url="{platform_url}").call(p)
                p = BrowserEval(
                    bridge=bridge,
                    expression="(async () => {{ for (let i=0; i<30; i++) {{ if (CupPlatform.recipes) return CupPlatform.recipes.capabilities.length; await new Promise(r=>setTimeout(r,200)); }} return -1; }})()",
                ).call(p)

                assert p.get("browser_ok") is True
                count = int(float(str(p.get("browser_eval", "0")).strip()))
                assert count >= 5, f"recipe count={{count}}"
                print("PASS: recipe_count")
        """)

    def test_multi_step_open_eval_close(self, platform_url):
        _run_browser_test(f"""
            from codeupipe import Payload
            from codeupipe.browser.playwright_bridge import PlaywrightBridge
            from codeupipe.browser import BrowserOpen, BrowserEval, BrowserClose

            with PlaywrightBridge(headless=True) as bridge:
                p = Payload()
                p = BrowserOpen(bridge=bridge, url="{platform_url}").call(p)
                p = BrowserEval(
                    bridge=bridge,
                    expression="document.querySelectorAll('.cup-dash-card').length",
                ).call(p)
                p = BrowserClose(bridge=bridge).call(p)

                assert p.get("browser_ok") is True
                count = int(float(str(p.get("browser_eval", "0")).strip()))
                assert count >= 6, f"dash card count={{count}}"
                print("PASS: full_lifecycle")
        """)
