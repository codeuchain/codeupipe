"""
Browser control bridge — subprocess wrapper around ``agent-browser`` CLI.

This is the single point of contact between codeupipe and the external
``agent-browser`` Node.js tool.  Every browser Filter delegates here.

The bridge is intentionally thin: build the command list, run it, return
stdout/stderr/returncode.  Filters interpret the output.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


__all__ = ["BrowserBridge", "BrowserResult"]


@dataclass(frozen=True)
class BrowserResult:
    """Immutable result from a single ``agent-browser`` invocation."""

    stdout: str
    stderr: str
    returncode: int
    command: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        """Primary output — stdout when successful, stderr on failure."""
        return self.stdout if self.ok else self.stderr


class BrowserBridge:
    """Subprocess bridge to ``agent-browser``.

    Parameters
    ----------
    executable : str | None
        Path to the agent-browser binary.  Resolved via ``shutil.which``
        when *None* (the default).
    timeout : int
        Per-command timeout in seconds (default 30).
    headed : bool
        Launch in headed mode so the user can see the browser.
    cdp_port : int | None
        Connect to an existing browser via CDP on this port instead of
        launching a new one.
    profile : str | None
        Path to a persistent browser profile directory.
    extra_args : list[str] | None
        Additional flags forwarded verbatim to every invocation.
    """

    def __init__(
        self,
        executable: Optional[str] = None,
        timeout: int = 30,
        headed: bool = False,
        cdp_port: Optional[int] = None,
        profile: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> None:
        self._executable = executable or shutil.which("agent-browser") or "npx"
        self._use_npx = self._executable == "npx"
        self._timeout = timeout
        self._headed = headed
        self._cdp_port = cdp_port
        self._profile = profile
        self._extra_args = extra_args or []

    # ── Public API ───────────────────────────────────────────────────

    def run(self, *args: str, timeout: Optional[int] = None) -> BrowserResult:
        """Execute an ``agent-browser`` command and return the result."""
        cmd = self._build_command(list(args))
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self._timeout,
            )
            return BrowserResult(
                stdout=proc.stdout.strip(),
                stderr=proc.stderr.strip(),
                returncode=proc.returncode,
                command=cmd,
            )
        except subprocess.TimeoutExpired:
            return BrowserResult(
                stdout="",
                stderr=f"Timeout after {timeout or self._timeout}s",
                returncode=-1,
                command=cmd,
            )
        except FileNotFoundError:
            return BrowserResult(
                stdout="",
                stderr=(
                    "agent-browser not found. "
                    "Install with: npm install -g agent-browser"
                ),
                returncode=-2,
                command=cmd,
            )

    # ── Convenience methods (thin wrappers around run) ───────────────

    def open(self, url: str) -> BrowserResult:
        return self.run("open", url)

    def snapshot(self, interactive: bool = True) -> BrowserResult:
        args = ["snapshot"]
        if interactive:
            args.append("-i")
        return self.run(*args)

    def click(self, selector: str) -> BrowserResult:
        return self.run("click", selector)

    def fill(self, selector: str, text: str) -> BrowserResult:
        return self.run("fill", selector, text)

    def type_text(self, selector: str, text: str) -> BrowserResult:
        return self.run("type", selector, text)

    def evaluate(self, expression: str) -> BrowserResult:
        return self.run("eval", expression)

    def screenshot(self, path: Optional[str] = None) -> BrowserResult:
        args = ["screenshot"]
        if path:
            args.append(path)
        return self.run(*args)

    def tabs(self) -> BrowserResult:
        return self.run("tab", "list")

    def raw(self, method: str, params: Optional[Dict[str, Any]] = None) -> BrowserResult:
        """Send a raw CDP command via ``agent-browser eval``.

        Uses ``eval`` to execute ``await page.context().browser().newBrowserCDPSession()``
        or falls back to the agent-browser CDP passthrough mechanism.
        For direct CDP, we construct a JS expression that uses the
        Chrome DevTools Protocol method.
        """
        # agent-browser doesn't have a direct `raw` command, so we
        # use eval to send CDP commands via Playwright's CDP session.
        js = self._build_cdp_eval(method, params)
        return self.run("eval", js)

    def close(self) -> BrowserResult:
        return self.run("close")

    def get(self, what: str, selector: Optional[str] = None) -> BrowserResult:
        args = ["get", what]
        if selector:
            args.append(selector)
        return self.run(*args)

    def wait(self, target: str) -> BrowserResult:
        return self.run("wait", target)

    def console(self) -> BrowserResult:
        return self.run("console")

    def errors(self) -> BrowserResult:
        return self.run("errors")

    # ── Internal ─────────────────────────────────────────────────────

    def _build_command(self, args: List[str]) -> List[str]:
        """Construct the full command line."""
        if self._use_npx:
            cmd = ["npx", "agent-browser"]
        else:
            cmd = [self._executable]

        # Global flags
        if self._headed:
            cmd.append("--headed")
        if self._cdp_port is not None:
            cmd.extend(["--cdp", str(self._cdp_port)])
        if self._profile:
            cmd.extend(["--profile", self._profile])
        cmd.extend(self._extra_args)

        # Subcommand + args
        cmd.extend(args)
        return cmd

    @staticmethod
    def _build_cdp_eval(method: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Build a JS expression that sends a raw CDP command."""
        params_json = json.dumps(params or {})
        # Use Playwright's CDP session API from within the page context
        return (
            f"(async () => {{"
            f"  const session = await window.__cdpSession__ || null;"
            f"  if (!session) return 'CDP session not available — use connect mode';"
            f"  return JSON.stringify(await session.send('{method}', {params_json}));"
            f"}})()"
        )
