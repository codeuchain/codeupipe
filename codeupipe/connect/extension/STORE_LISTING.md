# Chrome Web Store — Submission Checklist

## Store Listing Copy

**Extension Name:** CUP Platform Bridge

**Short Description** (132 chars max):
> Browser ↔ Desktop bridge for codeupipe pipelines. Connect web pages to native compute via Native Messaging, HTTP, or WASM.

**Detailed Description:**
> CUP Platform Bridge connects your browser to local compute power through codeupipe pipelines.
>
> **What it does:**
> • Bridges web pages to desktop applications via Chrome Native Messaging
> • Falls back to HTTP proxy or in-browser WASM when native host isn't available
> • Installs pipeline "recipes" — pre-built automations like page-to-pdf, form-fill, dom-audit
> • Dashboard shows live connection status to your local codeupipe runtime
>
> **How it works:**
> The extension injects a lightweight bridge (`window.cupBridge`) into pages on codeuchain.github.io and localhost. The Platform SPA dashboard lets you monitor connections, install recipes, and trigger pipelines. All processing happens locally — no data is sent to external servers.
>
> **Permissions explained:**
> • nativeMessaging — communicate with the local codeupipe Python runtime
> • storage — persist installed recipes and connection preferences
> • activeTab — read page content only when you explicitly trigger a recipe
>
> **Open source:** https://github.com/codeuchain/codeupipe

**Category:** Developer Tools

**Language:** English

## Assets Required

| Asset | Spec | Status |
|---|---|---|
| Icon 16×16 | PNG | ✅ `icons/icon-16.png` |
| Icon 48×48 | PNG | ✅ `icons/icon-48.png` |
| Icon 128×128 | PNG | ✅ `icons/icon-128.png` |
| Screenshot 1 | 1280×800 or 640×400 PNG | ❌ TODO — capture Platform SPA dashboard |
| Screenshot 2 | 1280×800 or 640×400 PNG | ❌ TODO — capture popup with connection status |
| Screenshot 3 | 1280×800 or 640×400 PNG | ❌ TODO — capture recipe store |
| Small promo tile | 440×280 PNG | ❌ Optional |
| Privacy policy URL | Live URL | ❌ TODO — host on GitHub Pages |

## Submission Steps

1. **Register** — https://chrome.google.com/webstore/devconsole ($5 one-time)
2. **Upload zip** — Use `cup-bridge-extension.zip` from `mkdocs build` output (`site/platform/`)
3. **Fill listing** — Copy the text above into the store listing form
4. **Upload screenshots** — At least 1, recommended 3
5. **Set privacy policy URL** — Point to hosted privacy policy page
6. **Select "Developer Tools"** category
7. **Submit for review** — Typically 1–3 business days

## Notes

- The extension zip is auto-built by `hooks/build_platform.py` on every `mkdocs build`
- Icons are placeholder PNGs (70 bytes each) — replace with real branded icons before submission
- The `icons/` directory must exist in the zip (manifest.json references `icons/icon-*.png`)
