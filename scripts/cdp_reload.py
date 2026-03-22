#!/usr/bin/env python3
"""CDP: reload extension + refresh platform page, then re-check."""
import asyncio
import json
import urllib.request
import websockets


async def main():
    targets = json.loads(
        urllib.request.urlopen("http://127.0.0.1:9222/json/list").read()
    )

    # Find platform page
    page_ws = None
    for t in targets:
        if "codeuchain.github.io/codeupipe/platform" in t.get("url", ""):
            page_ws = t["webSocketDebuggerUrl"]
            break

    if not page_ws:
        print("ERROR: Platform page not found")
        return

    print(f"Platform page: {page_ws}")

    async with websockets.connect(page_ws) as ws:
        # Step 1: Navigate to edge://extensions to trigger a reload
        # Actually, we can just reload the page — the content script will re-inject
        print("Reloading platform page...")
        await ws.send(json.dumps({
            "id": 1,
            "method": "Page.reload",
            "params": {"ignoreCache": True}
        }))
        resp = json.loads(await ws.recv())
        print(f"  Reload sent: {resp.get('result', resp)}")

        # Wait for page to load
        print("Waiting 5s for page load + content script injection...")
        await asyncio.sleep(5)

        # Step 2: Check state
        checks = [
            ("typeof window.cupBridge", "cupBridge type"),
            ("window.cupBridge ? window.cupBridge.detected : 'N/A'", "cupBridge.detected"),
            ("!!document.getElementById('cup-ext-status')", "status badge"),
            ("window.CupPlatform ? window.CupPlatform.tier : 'N/A'", "tier"),
        ]

        msg_id = 10
        for expr, label in checks:
            await ws.send(json.dumps({
                "id": msg_id,
                "method": "Runtime.evaluate",
                "params": {"expression": expr, "returnByValue": True}
            }))
            resp = json.loads(await ws.recv())
            val = resp.get("result", {}).get("result", {}).get("value", "ERROR")
            print(f"  {label}: {val}")
            msg_id += 1

        # Step 3: If badge exists, get its innerHTML
        await ws.send(json.dumps({
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": "document.getElementById('cup-ext-status') ? document.getElementById('cup-ext-status').innerText.substring(0, 200) : 'NO BADGE'",
                "returnByValue": True,
            }
        }))
        resp = json.loads(await ws.recv())
        val = resp.get("result", {}).get("result", {}).get("value", "ERROR")
        print(f"\n  Badge content: {val}")


asyncio.run(main())
