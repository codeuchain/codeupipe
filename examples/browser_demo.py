#!/usr/bin/env python3
"""
cup browser — The Full Iceberg
===============================

What the docs show you: 10 commands.
What you actually get:  60+ commands, 30+ flags, iOS simulator, network
interception, visual diffs, video recording, Chrome DevTools traces,
cookie management, auth vaults — the entire ``agent-browser`` surface.

Every ``BrowserBridge.run()`` call is a direct passthrough to the
underlying CLI.  Our 10 Filters are convenience wrappers for the most
common agent loop actions.  But ``run()`` accepts *any* agent-browser
subcommand and flags.

Requirements
------------
    pip install -e .               # codeupipe
    npm install -g agent-browser   # or: brew install agent-browser
    agent-browser install          # first time: download Chrome

Run
---
    python examples/browser_demo.py          # headless
    python examples/browser_demo.py --headed # watch it happen

This demo is organized as a tour of the hidden surface area that human
and agent users should know about.
"""

from __future__ import annotations

import sys
import time

from codeupipe.browser import BrowserBridge


def banner(title: str) -> None:
    width = 60
    print()
    print("═" * width)
    print(f"  {title}")
    print("═" * width)


def show(description: str, result) -> None:
    status = "✓" if result.ok else "✗"
    print(f"\n  {status} {description}")
    if result.output:
        # Indent output, truncate long output to 500 chars
        text = result.output[:500]
        for line in text.splitlines()[:15]:
            print(f"    {line}")
        if len(result.output) > 500:
            print(f"    ... ({len(result.output)} chars total)")


def main():
    headed = "--headed" in sys.argv

    # ── Create the bridge — this is the one object that talks to the browser ──
    bridge = BrowserBridge(headed=headed, timeout=30)
    print(f"\nBridge executable: {bridge._executable}")
    print(f"Headed mode: {headed}")

    # ══════════════════════════════════════════════════════════════════
    # TIER 1 — The 10 wrapped commands (what the docs tell you about)
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 1: The 10 documented commands")

    show("open url", bridge.open("https://example.com"))
    show("snapshot (interactive)", bridge.snapshot(interactive=True))
    show("get title", bridge.get("title"))
    show("get url", bridge.get("url"))
    show("evaluate JS", bridge.evaluate("document.title"))
    show("screenshot", bridge.screenshot())
    show("tabs", bridge.tabs())

    # ══════════════════════════════════════════════════════════════════
    # TIER 2 — Navigation nobody told you about
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 2: Navigation — back, forward, reload, wait")

    show("open second page", bridge.open("https://httpbin.org/html"))
    show("back", bridge.run("back"))
    show("forward", bridge.run("forward"))
    show("reload", bridge.run("reload"))
    show("wait 1000ms", bridge.run("wait", "1000"))

    # ══════════════════════════════════════════════════════════════════
    # TIER 3 — Input actions beyond click/fill
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 3: Rich input — hover, press, keyboard, scroll")

    show("open form page", bridge.open("https://httpbin.org/forms/post"))
    show("snapshot -i -c (compact)", bridge.run("snapshot", "-i", "-c"))
    show("scroll down 300px", bridge.run("scroll", "down", "300"))
    show("press Tab key", bridge.run("press", "Tab"))
    show("keyboard inserttext 'hello'", bridge.run("keyboard", "inserttext", "hello"))

    # ══════════════════════════════════════════════════════════════════
    # TIER 4 — Element inspection (is / find / get)
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 4: Element queries — find, is, get text/html/count")

    show("get element count", bridge.run("get", "count", "a"))
    show("get cdp-url", bridge.run("get", "cdp-url"))

    # find role button — discover clickable elements
    show("find role button click", bridge.run("find", "role", "button", "click"))

    # ══════════════════════════════════════════════════════════════════
    # TIER 5 — Viewport and device simulation
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 5: Device simulation — viewport, device, dark mode")

    show("set viewport 375x812 (iPhone)", bridge.run("set", "viewport", "375", "812"))
    show("screenshot as mobile", bridge.screenshot("mobile_view.png"))
    show("set color-scheme dark", bridge.run("set", "media", "dark"))
    show("reset viewport 1280x720", bridge.run("set", "viewport", "1280", "720"))

    # ══════════════════════════════════════════════════════════════════
    # TIER 6 — Network interception
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 6: Network — route, requests, offline mode")

    show("set offline ON", bridge.run("set", "offline", "on"))
    show("reload (offline)", bridge.run("reload"))
    show("set offline OFF", bridge.run("set", "offline", "off"))
    show("reload (back online)", bridge.run("reload"))
    show("network requests", bridge.run("network", "requests"))

    # ══════════════════════════════════════════════════════════════════
    # TIER 7 — Storage & cookies
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 7: Storage — cookies, localStorage, sessionStorage")

    show("cookies get", bridge.run("cookies", "get"))
    show("storage local", bridge.run("storage", "local"))

    # ══════════════════════════════════════════════════════════════════
    # TIER 8 — Debug & profiling
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 8: Debug — console, errors, trace, profiler, highlight")

    show("console logs", bridge.run("console"))
    show("page errors", bridge.run("errors"))

    # Tracing demo (start → action → stop → get trace file)
    show("trace start", bridge.run("trace", "start"))
    show("open page during trace", bridge.open("https://example.com"))
    show("trace stop (saves .zip)", bridge.run("trace", "stop", "demo_trace.zip"))

    # ══════════════════════════════════════════════════════════════════
    # TIER 9 — Visual diffs (snapshot-to-snapshot comparison)
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 9: Diff — compare snapshots, screenshots, URLs")

    show("first snapshot", bridge.snapshot(interactive=False))
    show("open different page", bridge.open("https://httpbin.org/html"))
    show("diff snapshot (before vs now)", bridge.run("diff", "snapshot"))

    # ══════════════════════════════════════════════════════════════════
    # TIER 10 — PDF, annotated screenshots, clipboard
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 10: Export — PDF, annotated screenshots, clipboard")

    show("save PDF", bridge.run("pdf", "demo_page.pdf"))
    show("annotated screenshot", bridge.run("screenshot", "--annotate", "annotated.png"))
    show("full-page screenshot", bridge.run("screenshot", "--full", "fullpage.png"))
    show("clipboard read", bridge.run("clipboard", "read"))

    # ══════════════════════════════════════════════════════════════════
    # TIER 11 — Sessions & auth vault
    # ══════════════════════════════════════════════════════════════════
    banner("TIER 11: Sessions & auth — persistent login state")

    show("session name", bridge.run("session"))
    show("session list", bridge.run("session", "list"))
    show("auth list (saved credentials)", bridge.run("auth", "list"))

    # ══════════════════════════════════════════════════════════════════
    # CLEANUP
    # ══════════════════════════════════════════════════════════════════
    banner("CLEANUP")
    show("close browser", bridge.close())

    # ══════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════
    banner("THE FULL SURFACE AREA")
    print("""
  What the docs show:     10 Filter classes, 10 CLI commands
  What bridge.run() gets: 60+ commands, 30+ flags

  ┌──────────────────────────────────────────────────────────┐
  │  Any agent-browser command works via bridge.run()        │
  │                                                          │
  │  bridge.run("back")                                      │
  │  bridge.run("scroll", "down", "500")                     │
  │  bridge.run("press", "Enter")                            │
  │  bridge.run("find", "role", "button", "click")           │
  │  bridge.run("set", "viewport", "375", "812")             │
  │  bridge.run("cookies", "get")                            │
  │  bridge.run("trace", "start")                            │
  │  bridge.run("diff", "snapshot")                          │
  │  bridge.run("pdf", "output.pdf")                         │
  │  bridge.run("network", "requests")                       │
  │  bridge.run("auth", "save", "myapp", "--url", "...")     │
  │                                                          │
  │  Plus all flags:                                         │
  │  BrowserBridge(headed=True, cdp_port=9222, profile="~")  │
  │  bridge.run("open", "url", "--json")                     │
  │  bridge.run("screenshot", "--annotate", "--full")         │
  └──────────────────────────────────────────────────────────┘

  The 10 Filters are the fast lane.
  bridge.run() is the everything lane.
""")


if __name__ == "__main__":
    main()
