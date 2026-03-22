"""
PlaywrightBridge — native Playwright backend for CUP Browser Filters.

Drop-in replacement for ``BrowserBridge`` that uses Playwright's Python
API directly instead of shelling out to ``agent-browser``.  This gives:

    - Zero Node.js dependency for browser automation
    - Full CDP access via ``page.context.browser.new_browser_cdp_session()``
    - Programmatic control suitable for SDK usage and CI pipelines
    - Same Filter interface — every CUP Browser Filter works unchanged

Usage::

    from codeupipe.browser.playwright_bridge import PlaywrightBridge
    from codeupipe.browser import BrowserOpen, BrowserEval

    with PlaywrightBridge(headless=True) as bridge:
        filt = BrowserOpen(bridge=bridge, url="https://example.com")
        result = filt.call(Payload())

Architecture:

    PlaywrightBridge is a context manager that owns a Playwright instance,
    Browser, BrowserContext, and Page.  Every method returns ``BrowserResult``
    for compatibility with the existing Filter layer.

    CLI mapping (future SDK):
        cup browser open <url>       → bridge.open(url)
        cup browser eval <expr>      → bridge.evaluate(expr)
        cup browser snapshot         → bridge.snapshot()
        cup browser screenshot       → bridge.screenshot(path)
        cup browser click <sel>      → bridge.click(sel)
        cup browser fill <sel> <txt> → bridge.fill(sel, txt)
        cup browser get <what>       → bridge.get(what, sel)
        cup browser close            → bridge.close()
        cup browser raw <method>     → bridge.raw(method, params)
"""

from __future__ import annotations

import json
import traceback
from typing import Any, Dict, List, Optional

from .bridge import BrowserResult

__all__ = ["PlaywrightBridge"]


class PlaywrightBridge:
    """Playwright-native browser bridge — same API as BrowserBridge.

    Parameters
    ----------
    headless : bool
        Run in headless mode (default True).
    slow_mo : int
        Milliseconds to slow down operations (useful for debugging).
    timeout : int
        Default timeout in milliseconds for page operations.
    browser_type : str
        One of 'chromium', 'firefox', 'webkit' (default 'chromium').
    channel : str or None
        Browser channel — 'msedge', 'chrome', 'chrome-beta', etc.
        When set, Playwright launches the *installed* browser instead of
        its bundled Chromium.  Use ``channel='msedge'`` for Edge.
    """

    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        timeout: int = 30000,
        browser_type: str = "chromium",
        channel: Optional[str] = None,
    ) -> None:
        self._headless = headless
        self._slow_mo = slow_mo
        self._timeout = timeout
        self._browser_type = browser_type
        self._channel = channel

        # Lazy — initialized on __enter__ or first use
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    # ── Context Manager ──────────────────────────────────────────────

    def __enter__(self):
        self._start()
        return self

    def __exit__(self, *exc):
        self._stop()
        return False

    def _start(self):
        """Launch Playwright + browser."""
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()

        launcher = getattr(self._pw, self._browser_type)
        launch_kwargs = {
            "headless": self._headless,
            "slow_mo": self._slow_mo,
        }
        if self._channel:
            launch_kwargs["channel"] = self._channel
        self._browser = launcher.launch(**launch_kwargs)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._page.set_default_timeout(self._timeout)

    def _stop(self):
        """Shut down Playwright."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None

    def _ensure_started(self):
        """Auto-start if used without context manager."""
        if self._page is None:
            self._start()

    @property
    def page(self):
        """Direct access to the Playwright Page for advanced use."""
        self._ensure_started()
        return self._page

    # ── BrowserBridge-compatible API ─────────────────────────────────

    def run(self, *args: str, timeout: Optional[int] = None) -> BrowserResult:
        """Compatibility shim — translates CLI args to Playwright calls.

        Most Filters call the convenience methods directly (open, eval, etc.)
        but some may call run() with raw agent-browser args.  We do our
        best to interpret them.
        """
        if not args:
            return BrowserResult(stdout="", stderr="No command", returncode=1)

        cmd = args[0]
        rest = args[1:]

        dispatch = {
            "open": lambda: self.open(rest[0] if rest else "about:blank"),
            "close": lambda: self.close(),
            "snapshot": lambda: self.snapshot(interactive="-i" in rest),
            "click": lambda: self.click(rest[0] if rest else ""),
            "fill": lambda: self.fill(rest[0] if len(rest) > 0 else "",
                                      rest[1] if len(rest) > 1 else ""),
            "eval": lambda: self.evaluate(rest[0] if rest else "null"),
            "screenshot": lambda: self.screenshot(rest[0] if rest else None),
            "tab": lambda: self.tabs(),
            "get": lambda: self.get(rest[0] if rest else "title",
                                    rest[1] if len(rest) > 1 else None),
        }

        handler = dispatch.get(cmd)
        if handler:
            return handler()
        return BrowserResult(
            stdout="", stderr=f"Unknown command: {cmd}", returncode=1
        )

    def open(self, url: str) -> BrowserResult:
        """Navigate to a URL."""
        self._ensure_started()
        try:
            self._page.goto(url, wait_until="domcontentloaded")
            # Best-effort wait for init scripts — don't block on Edge's
            # background sync / update traffic
            try:
                self._page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # network not idle is fine — page is already loaded
            return BrowserResult(
                stdout=f"Navigated to {url}",
                stderr="",
                returncode=0,
                command=["open", url],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["open", url],
            )

    def close(self) -> BrowserResult:
        """Close the browser."""
        try:
            self._stop()
            return BrowserResult(
                stdout="Browser closed",
                stderr="",
                returncode=0,
                command=["close"],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["close"],
            )

    def snapshot(self, interactive: bool = True) -> BrowserResult:
        """Get accessibility tree snapshot.

        Uses Playwright's ``locator.aria_snapshot()`` which returns a
        YAML-like accessibility tree.  Falls back to ``_format_a11y_tree``
        with CDP ``Accessibility.getFullAXTree`` when aria_snapshot is
        unavailable.
        """
        self._ensure_started()
        try:
            # Playwright ≥1.49 — native ARIA snapshot
            text = self._page.locator("body").aria_snapshot()
            return BrowserResult(
                stdout=text, stderr="", returncode=0,
                command=["snapshot"],
            )
        except AttributeError:
            pass  # fall through to CDP
        except Exception as e:
            # aria_snapshot exists but threw — still try CDP
            pass

        # Fallback: CDP Accessibility tree
        try:
            cdp = self._context.new_cdp_session(self._page)
            tree = cdp.send("Accessibility.getFullAXTree")
            cdp.detach()
            nodes = tree.get("nodes", [])
            lines = []
            for n in nodes:
                role = n.get("role", {}).get("value", "")
                name = n.get("name", {}).get("value", "")
                if role and role not in ("none", "generic", "InlineTextBox"):
                    display = f'{role} "{name}"' if name else role
                    lines.append(display)
            text = "\n".join(lines) if lines else "(empty)"
            return BrowserResult(
                stdout=text, stderr="", returncode=0,
                command=["snapshot"],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["snapshot"],
            )

    def click(self, selector: str) -> BrowserResult:
        """Click an element."""
        self._ensure_started()
        try:
            self._page.click(selector)
            return BrowserResult(
                stdout=f"Clicked {selector}",
                stderr="",
                returncode=0,
                command=["click", selector],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["click", selector],
            )

    def fill(self, selector: str, text: str) -> BrowserResult:
        """Fill a form field."""
        self._ensure_started()
        try:
            self._page.fill(selector, text)
            return BrowserResult(
                stdout=f"Filled {selector}",
                stderr="",
                returncode=0,
                command=["fill", selector, text],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["fill", selector, text],
            )

    def evaluate(self, expression: str) -> BrowserResult:
        """Evaluate JavaScript in the page context."""
        self._ensure_started()
        try:
            result = self._page.evaluate(expression)
            # Stringify non-string results
            if isinstance(result, str):
                stdout = result
            elif result is None:
                stdout = "null"
            else:
                stdout = json.dumps(result)
            return BrowserResult(
                stdout=stdout, stderr="", returncode=0,
                command=["eval", expression],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["eval", expression],
            )

    def screenshot(self, path: Optional[str] = None) -> BrowserResult:
        """Take a screenshot."""
        self._ensure_started()
        try:
            if path is None:
                import tempfile
                path = tempfile.mktemp(suffix=".png")
            self._page.screenshot(path=path)
            return BrowserResult(
                stdout=path, stderr="", returncode=0,
                command=["screenshot", path],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["screenshot"],
            )

    def tabs(self) -> BrowserResult:
        """List open tabs/pages."""
        self._ensure_started()
        try:
            pages = self._context.pages
            lines = []
            for i, pg in enumerate(pages):
                marker = " *" if pg == self._page else ""
                lines.append(f"[{i}]{marker} {pg.url}")
            return BrowserResult(
                stdout="\n".join(lines), stderr="", returncode=0,
                command=["tab", "list"],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["tab", "list"],
            )

    def get(self, what: str, selector: Optional[str] = None) -> BrowserResult:
        """Get page property: title, url, text, html, value."""
        self._ensure_started()
        try:
            result = ""
            if what == "title":
                result = self._page.title()
            elif what == "url":
                result = self._page.url
            elif what == "text":
                if selector:
                    result = self._page.locator(selector).inner_text()
                else:
                    result = self._page.locator("body").inner_text()
            elif what == "html":
                if selector:
                    result = self._page.locator(selector).inner_html()
                else:
                    result = self._page.content()
            elif what == "value":
                if selector:
                    result = self._page.locator(selector).input_value()
                else:
                    result = ""
            else:
                return BrowserResult(
                    stdout="", stderr=f"Unknown get target: {what}",
                    returncode=1, command=["get", what],
                )
            return BrowserResult(
                stdout=result, stderr="", returncode=0,
                command=["get", what],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["get", what],
            )

    def raw(self, method: str, params: Optional[Dict[str, Any]] = None) -> BrowserResult:
        """Send a raw CDP command."""
        self._ensure_started()
        try:
            cdp = self._context.new_cdp_session(self._page)
            result = cdp.send(method, params or {})
            cdp.detach()
            return BrowserResult(
                stdout=json.dumps(result) if result else "",
                stderr="",
                returncode=0,
                command=["raw", method],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["raw", method],
            )

    def wait(self, target: str) -> BrowserResult:
        """Wait for a selector or navigation."""
        self._ensure_started()
        try:
            self._page.wait_for_selector(target, timeout=self._timeout)
            return BrowserResult(
                stdout=f"Found {target}", stderr="", returncode=0,
                command=["wait", target],
            )
        except Exception as e:
            return BrowserResult(
                stdout="", stderr=str(e), returncode=1,
                command=["wait", target],
            )

    # ── Accessibility Tree Formatter ─────────────────────────────────

    @staticmethod
    def _format_a11y_tree(node: Optional[dict], interactive: bool = True,
                          depth: int = 0, counter: Optional[list] = None) -> str:
        """Recursively format the accessibility tree into text.

        Produces output similar to agent-browser's ``snapshot -i``:
            heading "CUP Platform" [level=1]
            link "Documentation" @e1
            textbox "Search" @e2
        """
        if node is None:
            return "(empty page)"

        if counter is None:
            counter = [0]

        lines = []
        indent = "  " * depth

        role = node.get("role", "")
        name = node.get("name", "")

        # Skip generic/non-useful nodes
        skip_roles = {"none", "generic", "StaticText"}
        if role not in skip_roles and (name or role):
            ref = ""
            interactive_roles = {
                "link", "button", "textbox", "checkbox", "radio",
                "combobox", "menuitem", "tab", "switch", "slider",
            }
            if interactive and role in interactive_roles:
                counter[0] += 1
                ref = f" @e{counter[0]}"

            display_name = f' "{name}"' if name else ""
            extra = ""
            if role == "heading":
                level = node.get("level", "")
                if level:
                    extra = f" [level={level}]"

            lines.append(f"{indent}{role}{display_name}{extra}{ref}")

        # Recurse children
        for child in node.get("children", []):
            child_text = PlaywrightBridge._format_a11y_tree(
                child, interactive, depth + 1, counter
            )
            if child_text:
                lines.append(child_text)

        return "\n".join(lines)
