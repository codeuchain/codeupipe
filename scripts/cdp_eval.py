#!/usr/bin/env python3
"""CDP check — evaluate JS on target page."""
import asyncio, json, sys, websockets

PAGE_ID = sys.argv[1] if len(sys.argv) > 1 else "106F8B2204979347CAA514A6BF0C781F"

async def main():
    ws_url = f"ws://127.0.0.1:9222/devtools/page/{PAGE_ID}"
    async with websockets.connect(ws_url) as ws:
        checks = [
            ("typeof window.cupBridge", "cupBridge type"),
            ("window.cupBridge ? window.cupBridge.detected : 'N/A'", "cupBridge.detected"),
            ("!!document.getElementById('cup-ext-status')", "badge injected"),
            ("window.CupPlatform ? window.CupPlatform.tier : 'N/A'", "CupPlatform.tier"),
            ("window.CupPlatform ? window.CupPlatform.detected : 'N/A'", "CupPlatform.detected"),
            ("document.title", "page title"),
        ]
        for i, (expr, label) in enumerate(checks, 1):
            await ws.send(json.dumps({"id": i, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
            resp = json.loads(await ws.recv())
            val = resp.get("result", {}).get("result", {}).get("value", "ERROR")
            print(f"  {label}: {val}")

        # Badge text
        await ws.send(json.dumps({"id": 99, "method": "Runtime.evaluate", "params": {
            "expression": "document.getElementById('cup-ext-status') ? document.getElementById('cup-ext-status').innerText.substring(0,300) : 'NO BADGE'",
            "returnByValue": True
        }}))
        resp = json.loads(await ws.recv())
        val = resp.get("result", {}).get("result", {}).get("value", "?")
        print(f"\n  Badge text:\n{val}")

asyncio.run(main())
