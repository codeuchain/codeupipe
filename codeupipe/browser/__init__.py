"""
codeupipe.browser — Browser control via Chrome DevTools Protocol.

Provides CUP Filters that wrap ``agent-browser`` CLI commands for
programmatic browser control from pipelines and the ``cup browser``
subcommand.

Architecture
------------
- ``BrowserBridge`` — subprocess wrapper (single point of contact)
- One Filter per browser action (one class per file)
- ``cup browser <cmd>`` CLI routes to Filters via pipelines

All browser Filters read/write standard Payload keys:

    browser_url       : str   — current page URL
    browser_snapshot  : str   — accessibility tree text
    browser_eval      : str   — JS evaluation result
    browser_screenshot: str   — path to screenshot file
    browser_tabs      : str   — tab list output
    browser_output    : str   — raw output from last command
    browser_error     : str   — error message (if any)
    browser_ok        : bool  — whether last command succeeded
"""

from .bridge import BrowserBridge, BrowserResult
from .browser_open import BrowserOpen
from .browser_close import BrowserClose
from .browser_snapshot import BrowserSnapshot
from .browser_click import BrowserClick
from .browser_fill import BrowserFill
from .browser_eval import BrowserEval
from .browser_screenshot import BrowserScreenshot
from .browser_tabs import BrowserTabs
from .browser_raw import BrowserRaw
from .browser_get import BrowserGet

__all__ = [
    "BrowserBridge",
    "BrowserClick",
    "BrowserClose",
    "BrowserEval",
    "BrowserFill",
    "BrowserGet",
    "BrowserOpen",
    "BrowserRaw",
    "BrowserResult",
    "BrowserScreenshot",
    "BrowserSnapshot",
    "BrowserTabs",
]
