"""
Tests for codeupipe.browser — Browser control Filters and BrowserBridge.

Three tiers:
    1. Unit tests    — mock BrowserBridge, verify Filter Payload contracts
    2. Integration   — real subprocess calls, verify BrowserBridge behavior
    3. E2E           — real browser, full pipeline open→snapshot→click→close

E2E tests require ``agent-browser`` installed and are marked with
``@pytest.mark.e2e``.  Skip in CI with ``pytest -m "not e2e"``.
"""

import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from codeupipe import Payload, Pipeline
from codeupipe.testing import run_filter, assert_payload, assert_keys

from codeupipe.browser import (
    BrowserBridge,
    BrowserResult,
    BrowserOpen,
    BrowserClose,
    BrowserSnapshot,
    BrowserClick,
    BrowserFill,
    BrowserEval,
    BrowserScreenshot,
    BrowserTabs,
    BrowserRaw,
    BrowserGet,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _mock_bridge(stdout: str = "", stderr: str = "", returncode: int = 0) -> BrowserBridge:
    """Create a BrowserBridge with mocked subprocess.run."""
    bridge = BrowserBridge()
    mock_result = BrowserResult(
        stdout=stdout, stderr=stderr, returncode=returncode, command=[]
    )
    bridge.run = MagicMock(return_value=mock_result)
    return bridge


def _ok_bridge(stdout: str = "✓ OK") -> BrowserBridge:
    return _mock_bridge(stdout=stdout, returncode=0)


def _fail_bridge(stderr: str = "✗ Error") -> BrowserBridge:
    return _mock_bridge(stderr=stderr, returncode=1)


def _has_agent_browser() -> bool:
    """Check if agent-browser is available on the system."""
    try:
        result = subprocess.run(
            ["npx", "agent-browser", "--version"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# Skip E2E tests if agent-browser is not installed
e2e = pytest.mark.skipif(
    not _has_agent_browser(),
    reason="agent-browser not installed",
)


# ═══════════════════════════════════════════════════════════════════════
# TIER 1 — Unit Tests (mocked bridge, verify Payload contracts)
# ═══════════════════════════════════════════════════════════════════════


class TestBrowserResult:
    """Tests for the BrowserResult dataclass."""

    def test_ok_when_zero_returncode(self):
        r = BrowserResult(stdout="ok", stderr="", returncode=0, command=[])
        assert r.ok is True

    def test_not_ok_when_nonzero(self):
        r = BrowserResult(stdout="", stderr="error", returncode=1, command=[])
        assert r.ok is False

    def test_output_returns_stdout_on_success(self):
        r = BrowserResult(stdout="hello", stderr="warn", returncode=0, command=[])
        assert r.output == "hello"

    def test_output_returns_stderr_on_failure(self):
        r = BrowserResult(stdout="", stderr="bad", returncode=1, command=[])
        assert r.output == "bad"

    def test_frozen(self):
        r = BrowserResult(stdout="x", stderr="", returncode=0, command=[])
        with pytest.raises(AttributeError):
            r.stdout = "changed"


class TestBrowserBridgeCommandBuilding:
    """Tests that BrowserBridge builds the correct command arrays."""

    def test_basic_command(self):
        bridge = BrowserBridge(executable="/usr/bin/agent-browser")
        cmd = bridge._build_command(["open", "https://example.com"])
        assert cmd == ["/usr/bin/agent-browser", "open", "https://example.com"]

    def test_npx_fallback(self):
        bridge = BrowserBridge(executable="npx")
        cmd = bridge._build_command(["snapshot", "-i"])
        assert cmd[:2] == ["npx", "agent-browser"]
        assert "snapshot" in cmd
        assert "-i" in cmd

    def test_headed_flag(self):
        bridge = BrowserBridge(executable="/usr/bin/ab", headed=True)
        cmd = bridge._build_command(["open", "x"])
        assert "--headed" in cmd

    def test_cdp_port(self):
        bridge = BrowserBridge(executable="/usr/bin/ab", cdp_port=9222)
        cmd = bridge._build_command(["snapshot"])
        assert "--cdp" in cmd
        assert "9222" in cmd

    def test_profile_flag(self):
        bridge = BrowserBridge(executable="/usr/bin/ab", profile="/tmp/profile")
        cmd = bridge._build_command(["open", "x"])
        assert "--profile" in cmd
        assert "/tmp/profile" in cmd

    def test_extra_args(self):
        bridge = BrowserBridge(executable="/usr/bin/ab", extra_args=["--json"])
        cmd = bridge._build_command(["snapshot"])
        assert "--json" in cmd


class TestBrowserOpenFilter:
    """Unit tests for BrowserOpen filter."""

    def test_sets_browser_url(self):
        bridge = _ok_bridge("✓ Example Domain\n  https://example.com/")
        f = BrowserOpen(bridge, url="https://example.com")
        result = run_filter(f, {})
        assert_payload(result, browser_url="https://example.com")
        assert_keys(result, "browser_ok", "browser_output")

    def test_reads_url_from_payload(self):
        bridge = _ok_bridge()
        f = BrowserOpen(bridge)
        result = run_filter(f, {"browser_url": "https://test.com"})
        assert_payload(result, browser_url="https://test.com")

    def test_raises_without_url(self):
        bridge = _ok_bridge()
        f = BrowserOpen(bridge)
        with pytest.raises(ValueError, match="browser_url"):
            run_filter(f, {})

    def test_ok_true_on_success(self):
        bridge = _ok_bridge()
        f = BrowserOpen(bridge, url="https://example.com")
        result = run_filter(f, {})
        assert result.get("browser_ok") is True

    def test_ok_false_on_failure(self):
        bridge = _fail_bridge("Navigation failed")
        f = BrowserOpen(bridge, url="https://bad.url")
        result = run_filter(f, {})
        assert result.get("browser_ok") is False


class TestBrowserCloseFilter:
    """Unit tests for BrowserClose filter."""

    def test_sets_ok_and_output(self):
        bridge = _ok_bridge("✓ Browser closed")
        f = BrowserClose(bridge)
        result = run_filter(f, {})
        assert result.get("browser_ok") is True
        assert_keys(result, "browser_output")


class TestBrowserSnapshotFilter:
    """Unit tests for BrowserSnapshot filter."""

    def test_sets_snapshot_text(self):
        tree = '- heading "Test" [level=1, ref=e1]\n- link "Click" [ref=e2]'
        bridge = _ok_bridge(tree)
        f = BrowserSnapshot(bridge)
        result = run_filter(f, {})
        assert result.get("browser_snapshot") == tree
        assert result.get("browser_ok") is True

    def test_empty_snapshot_on_failure(self):
        bridge = _fail_bridge("No page loaded")
        f = BrowserSnapshot(bridge)
        result = run_filter(f, {})
        assert result.get("browser_snapshot") == ""
        assert result.get("browser_ok") is False


class TestBrowserClickFilter:
    """Unit tests for BrowserClick filter."""

    def test_click_by_constructor_selector(self):
        bridge = _ok_bridge("✓ Clicked")
        f = BrowserClick(bridge, selector="@e2")
        result = run_filter(f, {})
        assert result.get("browser_ok") is True

    def test_click_by_payload_selector(self):
        bridge = _ok_bridge("✓ Clicked")
        f = BrowserClick(bridge)
        result = run_filter(f, {"browser_selector": ".btn"})
        assert result.get("browser_ok") is True

    def test_raises_without_selector(self):
        bridge = _ok_bridge()
        f = BrowserClick(bridge)
        with pytest.raises(ValueError, match="browser_selector"):
            run_filter(f, {})


class TestBrowserFillFilter:
    """Unit tests for BrowserFill filter."""

    def test_fill_with_constructor_args(self):
        bridge = _ok_bridge()
        f = BrowserFill(bridge, selector="#email", text="test@example.com")
        result = run_filter(f, {})
        assert result.get("browser_ok") is True

    def test_fill_from_payload(self):
        bridge = _ok_bridge()
        f = BrowserFill(bridge)
        result = run_filter(f, {"browser_selector": "#name", "browser_text": "Alice"})
        assert result.get("browser_ok") is True

    def test_raises_without_selector(self):
        bridge = _ok_bridge()
        f = BrowserFill(bridge)
        with pytest.raises(ValueError, match="browser_selector"):
            run_filter(f, {})


class TestBrowserEvalFilter:
    """Unit tests for BrowserEval filter."""

    def test_returns_eval_result(self):
        bridge = _ok_bridge('"Example Domain"')
        f = BrowserEval(bridge, expression="document.title")
        result = run_filter(f, {})
        assert result.get("browser_eval") == '"Example Domain"'
        assert result.get("browser_ok") is True

    def test_raises_without_expression(self):
        bridge = _ok_bridge()
        f = BrowserEval(bridge)
        with pytest.raises(ValueError, match="browser_expression"):
            run_filter(f, {})


class TestBrowserScreenshotFilter:
    """Unit tests for BrowserScreenshot filter."""

    def test_sets_screenshot_path(self):
        bridge = _ok_bridge("✓ Screenshot saved to /tmp/shot.png")
        f = BrowserScreenshot(bridge, path="/tmp/shot.png")
        result = run_filter(f, {})
        assert result.get("browser_screenshot") == "/tmp/shot.png"
        assert result.get("browser_ok") is True


class TestBrowserTabsFilter:
    """Unit tests for BrowserTabs filter."""

    def test_returns_tab_list(self):
        tabs_output = "1. https://example.com/ (Example Domain)"
        bridge = _ok_bridge(tabs_output)
        f = BrowserTabs(bridge)
        result = run_filter(f, {})
        assert result.get("browser_tabs") == tabs_output


class TestBrowserRawFilter:
    """Unit tests for BrowserRaw filter."""

    def test_returns_raw_result(self):
        bridge = _ok_bridge('{"result": {}}')
        f = BrowserRaw(bridge, method="Page.getNavigationHistory")
        result = run_filter(f, {})
        assert result.get("browser_raw") == '{"result": {}}'

    def test_raises_without_method(self):
        bridge = _ok_bridge()
        f = BrowserRaw(bridge)
        with pytest.raises(ValueError, match="browser_cdp_method"):
            run_filter(f, {})


class TestBrowserGetFilter:
    """Unit tests for BrowserGet filter."""

    def test_get_title(self):
        bridge = _ok_bridge("Example Domain")
        f = BrowserGet(bridge, what="title")
        result = run_filter(f, {})
        assert result.get("browser_get_result") == "Example Domain"

    def test_raises_without_what(self):
        bridge = _ok_bridge()
        f = BrowserGet(bridge)
        with pytest.raises(ValueError, match="browser_get_what"):
            run_filter(f, {})


# ═══════════════════════════════════════════════════════════════════════
# TIER 2 — Integration Tests (real subprocess, verify BrowserBridge)
# ═══════════════════════════════════════════════════════════════════════


class TestBrowserBridgeIntegration:
    """Integration tests — real subprocess calls."""

    @e2e
    def test_run_returns_browser_result(self):
        bridge = BrowserBridge(timeout=30)
        result = bridge.run("--version")
        assert isinstance(result, BrowserResult)
        assert result.ok is True
        assert "agent-browser" in result.stdout

    def test_timeout_returns_error(self):
        bridge = BrowserBridge(executable="/usr/bin/sleep", timeout=1)
        # This will try to run "sleep open https://example.com" which
        # will either fail immediately or timeout — either way we test
        # error handling. We use a direct patch instead.
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=1)):
            result = bridge.run("open", "https://example.com")
            assert result.ok is False
            assert "Timeout" in result.stderr

    def test_missing_executable_returns_error(self):
        bridge = BrowserBridge(executable="/nonexistent/binary")
        result = bridge.run("--version")
        assert result.ok is False
        assert "not found" in result.stderr


# ═══════════════════════════════════════════════════════════════════════
# TIER 3 — E2E Tests (real browser, full pipeline)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestBrowserE2E:
    """End-to-end tests with a real browser.

    These tests actually launch Chrome, navigate to pages, take snapshots,
    and verify real output. They are the ultimate contract verification.

    Run with: ``pytest -m e2e tests/test_browser_filters.py``
    """

    @pytest.fixture(autouse=True)
    def bridge(self):
        """Shared bridge for all E2E tests. Closes browser after each test."""
        self._bridge = BrowserBridge(timeout=30)
        yield self._bridge
        self._bridge.close()

    def test_open_and_get_title(self):
        result = self._bridge.open("https://example.com")
        assert result.ok, f"open failed: {result.stderr}"
        assert "Example Domain" in result.stdout

    def test_snapshot_returns_accessibility_tree(self):
        self._bridge.open("https://example.com")
        result = self._bridge.snapshot(interactive=True)
        assert result.ok, f"snapshot failed: {result.stderr}"
        assert "ref=" in result.stdout
        assert "Example Domain" in result.stdout or "heading" in result.stdout

    def test_eval_returns_document_title(self):
        self._bridge.open("https://example.com")
        result = self._bridge.evaluate("document.title")
        assert result.ok, f"eval failed: {result.stderr}"
        assert "Example Domain" in result.stdout

    def test_screenshot_creates_file(self):
        self._bridge.open("https://example.com")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            result = self._bridge.screenshot(path)
            assert result.ok, f"screenshot failed: {result.stderr}"
            assert os.path.exists(path)
            assert os.path.getsize(path) > 1000  # Should be a real image
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_get_title(self):
        self._bridge.open("https://example.com")
        result = self._bridge.get("title")
        assert result.ok, f"get title failed: {result.stderr}"
        assert "Example Domain" in result.stdout

    def test_get_url(self):
        self._bridge.open("https://example.com")
        result = self._bridge.get("url")
        assert result.ok, f"get url failed: {result.stderr}"
        assert "example.com" in result.stdout

    def test_tabs_lists_open_pages(self):
        self._bridge.open("https://example.com")
        result = self._bridge.tabs()
        assert result.ok, f"tabs failed: {result.stderr}"
        # Should list at least one tab
        assert len(result.stdout) > 0


@pytest.mark.e2e
class TestBrowserPipelineE2E:
    """E2E test of a full CUP pipeline with browser Filters."""

    def test_full_pipeline_open_snapshot_eval_close(self):
        """The definitive contract test: build a pipeline of browser
        Filters and verify the full flow produces real results."""
        bridge = BrowserBridge(timeout=30)

        try:
            pipeline = Pipeline()
            pipeline.add_filter(BrowserOpen(bridge, url="https://example.com"))
            pipeline.add_filter(BrowserSnapshot(bridge, interactive=True))
            pipeline.add_filter(BrowserEval(bridge, expression="document.title"))

            import asyncio
            result = asyncio.run(pipeline.run(Payload({})))

            # Verify all payload keys are set
            assert result.get("browser_ok") is True
            assert result.get("browser_url") == "https://example.com"
            assert "ref=" in result.get("browser_snapshot", "")
            assert "Example Domain" in result.get("browser_eval", "")
        finally:
            bridge.close()

    def test_screenshot_pipeline(self):
        """Pipeline that navigates and screenshots."""
        bridge = BrowserBridge(timeout=30)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name

        try:
            pipeline = Pipeline()
            pipeline.add_filter(BrowserOpen(bridge, url="https://example.com"))
            pipeline.add_filter(BrowserScreenshot(bridge, path=path))

            import asyncio
            result = asyncio.run(pipeline.run(Payload({})))

            assert result.get("browser_ok") is True
            assert os.path.exists(path)
            assert os.path.getsize(path) > 1000
        finally:
            bridge.close()
            if os.path.exists(path):
                os.unlink(path)
