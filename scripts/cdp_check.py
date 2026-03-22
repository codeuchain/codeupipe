#!/usr/bin/env python3
"""CDP diagnostic — check extension state on the platform page."""
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("ERROR: pip3 install websockets")
    sys.exit(1)


async def main():
    # Find the platform page target
    import urllib.request
    targets = json.loads(
        urllib.request.urlopen("http://127.0.0.1:9222/json/list").read()
    )

    page_id = None
    for t in targets:
        if "codeuchain.github.io/codeupipe/platform" in t.get("url", ""):
            page_id = t["id"]
            break

    if not page_id:
        print("ERROR: Platform page not found in CDP targets")
        print("Open tabs:")
        for t in targets:
            if t.get("type") == "page":
                print(f"  {t['type']}: {t['url']}")
        sys.exit(1)

    ws_url = f"ws://127.0.0.1:9222/devtools/page/{page_id}"
    print(f"Connecting to: {ws_url}")

    async with websockets.connect(ws_url) as ws:
        checks = [
            ("typeof window.cupBridge", "cupBridge type"),
            ("window.cupBridge ? window.cupBridge.detected : 'N/A'", "cupBridge.detected"),
            ("!!document.getElementById('cup-ext-status')", "status badge injected"),
            ("typeof window.CupPlatform", "CupPlatform type"),
            ("window.CupPlatform ? window.CupPlatform.detected : 'N/A'", "CupPlatform.detected"),
            ("window.CupPlatform ? window.CupPlatform.tier : 'N/A'", "CupPlatform.tier"),
            ("document.title", "page title"),
            ("document.querySelectorAll('script').length", "script tags"),
        ]

        msg_id = 1
        for expr, label in checks:
            await ws.send(json.dumps({
                "id": msg_id,
                "method": "Runtime.evaluate",
                "params": {"expression": expr, "returnByValue": True}
            }))
            resp = json.loads(await ws.recv())
            result = resp.get("result", {}).get("result", {})
            val = result.get("value", result.get("description", "ERROR"))
            print(f"  {label}: {val}")
            msg_id += 1

        # Also check for our service worker among extension targets
        print("\n  CUP service workers:")
        for t in targets:
            if t.get("type") == "service_worker" and "service-worker" in t.get("url", ""):
                print(f"    {t['title']}")

        # Check chrome.runtime availability from content script perspective
        await ws.send(json.dumps({
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": "typeof chrome !== 'undefined' && typeof chrome.runtime !== 'undefined'",
                "returnByValue": True,
            }
        }))
        resp = json.loads(await ws.recv())
        val = resp.get("result", {}).get("result", {}).get("value", "ERROR")
        print(f"\n  chrome.runtime accessible from page: {val}")


asyncio.run(main())
