# codeupipe Browser — Agent Reference

> `curl https://codeuchain.github.io/codeupipe/agents/browser.txt`

---

## What You Get

`codeupipe.browser` wraps [agent-browser](https://github.com/nichochar/agent-browser) — a full Chrome DevTools Protocol CLI. Our 10 Filter classes cover the common agent-loop actions. But `BrowserBridge.run()` is a **direct passthrough** to the entire underlying CLI: **60+ commands and 30+ flags**.

**The 10 Filters are the fast lane. `bridge.run()` is the everything lane.**

### Install

```bash
pip install codeupipe                  # the framework
npm install -g agent-browser           # the browser CLI
agent-browser install                  # download Chrome (first time)
```

---

## Quick Start — CLI

```bash
cup browser-open https://example.com        # open URL
cup browser-snapshot                        # accessibility tree with @refs
cup browser-click @e2                       # click element by @ref
cup browser-fill @e3 "hello@example.com"    # fill form field
cup browser-eval "document.title"           # evaluate JS
cup browser-get title                       # get page title
cup browser-screenshot /tmp/shot.png        # capture PNG
cup browser-tabs                            # list open tabs
cup browser-raw Page.getNavigationHistory   # raw CDP method
cup browser-close                           # close session

# Flags (apply to any browser command)
cup browser-open https://x.com --headed         # visible browser
cup browser-snapshot --cdp-port 9222            # attach to existing Chrome
cup browser-open https://x.com --profile myapp  # persistent sessions
```

## Quick Start — Python

```python
from codeupipe.browser import BrowserBridge

bridge = BrowserBridge(headed=True)

# Wrapped convenience methods
bridge.open("https://example.com")
bridge.snapshot(interactive=True)
bridge.click("@e2")
bridge.fill("@e3", "hello")
bridge.evaluate("document.title")
bridge.screenshot("page.png")
bridge.tabs()
bridge.close()
```

## Quick Start — Pipeline

```python
from codeupipe import Payload, Pipeline
from codeupipe.browser import BrowserBridge, BrowserOpen, BrowserSnapshot, BrowserClick

bridge = BrowserBridge()
pipeline = Pipeline()
pipeline.add_filter(BrowserOpen(bridge=bridge, url="https://example.com"))
pipeline.add_filter(BrowserSnapshot(bridge=bridge))
pipeline.add_filter(BrowserClick(bridge=bridge, selector="@e2"))

result = pipeline.run(Payload())
print(result.get("browser_snapshot"))
```

---

## The Full Surface Area

Everything below works via `bridge.run()` — these are not individually wrapped as Filters, but they all work right now.

### Input Actions

```python
bridge.run("dblclick", "@e1")                  # double-click
bridge.run("type", "@e1", "hello")             # type into element
bridge.run("press", "Enter")                   # press key
bridge.run("press", "Control+a")               # key combo
bridge.run("keyboard", "inserttext", "hello")  # raw keyboard input
bridge.run("hover", "@e1")                     # hover element
bridge.run("focus", "@e1")                     # focus element
bridge.run("check", "@e1")                     # check checkbox
bridge.run("uncheck", "@e1")                   # uncheck checkbox
bridge.run("select", "@e1", "option_value")    # select dropdown
bridge.run("drag", "@e1", "@e2")               # drag and drop
bridge.run("upload", "@e1", "/path/to/file")   # file upload
bridge.run("download", "@e1", "/tmp/")         # download by clicking
bridge.run("scroll", "down", "500")            # scroll 500px
bridge.run("scrollintoview", "@e1")            # scroll element into view
```

### Navigation

```python
bridge.run("back")                             # browser back
bridge.run("forward")                          # browser forward
bridge.run("reload")                           # reload page
bridge.run("wait", "2000")                     # wait 2 seconds
bridge.run("wait", "@e1")                      # wait for element
bridge.run("wait", "--load", "networkidle")    # wait for network idle
```

### Element Queries

```python
bridge.run("find", "role", "button", "click")         # find by ARIA role + act
bridge.run("find", "text", "Submit", "click")          # find by text + act
bridge.run("find", "label", "Email", "fill", "a@b.c")  # find by label + fill
bridge.run("find", "placeholder", "Search...", "fill", "query")
bridge.run("find", "testid", "submit-btn", "click")    # find by data-testid
bridge.run("is", "visible", "@e1")                     # check visibility
bridge.run("is", "enabled", "@e1")                     # check enabled state
bridge.run("is", "checked", "@e1")                     # check checked state
bridge.run("get", "text", "@e1")                       # get element text
bridge.run("get", "html", "@e1")                       # get element HTML
bridge.run("get", "value", "@e1")                      # get input value
bridge.run("get", "attr", "href", "@e1")               # get attribute
bridge.run("get", "count", "a")                        # count matching elements
bridge.run("get", "box", "@e1")                        # bounding box
bridge.run("get", "styles", "@e1")                     # computed styles
bridge.run("get", "cdp-url")                           # WebSocket debug URL
```

### Mouse Control

```python
bridge.run("mouse", "move", "100", "200")    # move to coordinates
bridge.run("mouse", "down")                  # mouse button down
bridge.run("mouse", "up")                    # mouse button up
bridge.run("mouse", "wheel", "300")          # scroll wheel
```

### Viewport & Device Simulation

```python
bridge.run("set", "viewport", "375", "812")   # iPhone dimensions
bridge.run("set", "device", "iPhone 15 Pro")  # named device preset
bridge.run("set", "geo", "37.7749", "-122.4194")  # geolocation
bridge.run("set", "media", "dark")             # dark mode
bridge.run("set", "media", "light", "reduced-motion")
```

### Network Control

```python
bridge.run("set", "offline", "on")             # simulate offline
bridge.run("set", "offline", "off")            # back online
bridge.run("set", "headers", '{"X-Custom": "value"}')
bridge.run("set", "credentials", "user", "pass")
bridge.run("network", "route", "*.js", "--abort")  # block JS files
bridge.run("network", "route", "/api/*", "--body", '{"mock": true}')
bridge.run("network", "unroute", "*.js")        # remove route
bridge.run("network", "requests")               # captured requests
bridge.run("network", "requests", "--filter", "api")
```

### Storage & Cookies

```python
bridge.run("cookies", "get")                   # list all cookies
bridge.run("cookies", "set", "--url", "https://x.com",
           "--domain", "x.com", "--name", "session",
           "--value", "abc123", "--httpOnly", "--secure")
bridge.run("cookies", "clear")                 # clear all
bridge.run("storage", "local")                 # dump localStorage
bridge.run("storage", "session")               # dump sessionStorage
```

### Debug & Profiling

```python
bridge.run("console")                          # view console logs
bridge.run("console", "--clear")               # clear + view
bridge.run("errors")                           # view page errors
bridge.run("highlight", "@e1")                 # highlight element
bridge.run("inspect")                          # open Chrome DevTools
bridge.run("trace", "start")                   # start trace recording
bridge.run("trace", "stop", "trace.zip")       # save trace file
bridge.run("profiler", "start")                # start CPU profiler
bridge.run("profiler", "stop", "profile.json") # save profile
bridge.run("record", "start", "video.webm")    # start video recording
bridge.run("record", "stop")                   # stop and save
```

### Export

```python
bridge.run("pdf", "page.pdf")                  # save as PDF
bridge.run("screenshot", "--annotate", "a.png") # labeled screenshot (for vision models)
bridge.run("screenshot", "--full", "full.png")  # full page screenshot
bridge.run("clipboard", "read")                # read clipboard
bridge.run("clipboard", "write", "text")       # write to clipboard
```

### Visual Diffs

```python
bridge.snapshot()                              # take baseline
bridge.open("https://other-page.com")
bridge.run("diff", "snapshot")                 # diff accessibility trees
bridge.run("diff", "screenshot", "--baseline", "before.png")  # visual diff
bridge.run("diff", "url", "https://a.com", "https://b.com")   # compare two pages
```

### Sessions & Auth Vault

```python
bridge.run("session")                          # current session name
bridge.run("session", "list")                  # list active sessions
bridge.run("auth", "save", "myapp",
           "--url", "https://app.com/login",
           "--username", "user@example.com",
           "--password", "secret")             # save auth profile
bridge.run("auth", "login", "myapp")           # replay saved login
bridge.run("auth", "list")                     # list saved profiles
bridge.run("auth", "show", "myapp")            # show profile metadata
bridge.run("auth", "delete", "myapp")          # delete profile
```

---

## Global Flags

These work on any command. Pass via `BrowserBridge(extra_args=[...])` or inline with `bridge.run()`:

| Flag | Purpose |
|------|---------|
| `--json` | Machine-readable JSON output (best for agents) |
| `--headed` | Show browser window (visible mode) |
| `--cdp <port>` | Connect to existing browser via Chrome DevTools Protocol |
| `--profile <path>` | Persistent browser profile (cookies, cache survive restarts) |
| `--session-name <name>` | Auto-persist cookies/localStorage by name |
| `--state <path>` | Load saved auth state from JSON file |
| `--auto-connect` | Discover and attach to a running Chrome instance |
| `--annotate` | Numbered labels on screenshots (for vision models) |
| `--full` | Full-page screenshot |
| `--color-scheme dark\|light` | Force color scheme |
| `--proxy <url>` | HTTP/SOCKS proxy |
| `--proxy-bypass <hosts>` | Skip proxy for specific hosts |
| `--user-agent <ua>` | Custom User-Agent string |
| `--ignore-https-errors` | Accept self-signed certificates |
| `--allowed-domains <list>` | Restrict navigation to specific domains |
| `--action-policy <path>` | JSON policy controlling allowed actions |
| `--confirm-actions <list>` | Require confirmation for destructive actions |
| `--max-output <n>` | Truncate output to N characters |
| `--content-boundaries` | Wrap output in boundary markers |
| `--engine lightpanda` | Use LightPanda engine instead of Chrome |
| `--extension <path>` | Load browser extensions (repeatable) |
| `--args <args>` | Raw Chromium launch args |

Example — structured JSON output for agent parsing:

```python
bridge = BrowserBridge(extra_args=["--json"])
result = bridge.open("https://example.com")
import json
data = json.loads(result.output)  # structured result
```

---

## Payload Keys

Filters read/write these keys on the Payload flowing through pipelines:

| Key | Type | Set By |
|-----|------|--------|
| `browser_url` | str | BrowserOpen |
| `browser_snapshot` | str | BrowserSnapshot |
| `browser_eval` | str | BrowserEval |
| `browser_screenshot` | str | BrowserScreenshot |
| `browser_tabs` | str | BrowserTabs |
| `browser_raw` | str | BrowserRaw |
| `browser_get_result` | str | BrowserGet |
| `browser_ok` | bool | All filters |
| `browser_output` | str | All filters |
| `browser_error` | str | All filters (on failure) |
| `browser_selector` | str | Read by BrowserClick, BrowserFill |
| `browser_text` | str | Read by BrowserFill |
| `browser_expression` | str | Read by BrowserEval |
| `browser_cdp_method` | str | Read by BrowserRaw |
| `browser_cdp_params` | str | Read by BrowserRaw |
| `browser_get_what` | str | Read by BrowserGet |
| `browser_get_selector` | str | Read by BrowserGet |
| `browser_interactive` | bool | Read by BrowserSnapshot |
| `browser_screenshot_path` | str | Read by BrowserScreenshot |

---

## Agent Loop Pattern

The canonical agent loop using `cup browser`:

```python
from codeupipe.browser import BrowserBridge

bridge = BrowserBridge(extra_args=["--json"])

# 1. Navigate
bridge.open("https://target-site.com")

# 2. Observe (accessibility tree — structured, not pixel-based)
snap = bridge.snapshot(interactive=True)
print(snap.output)  # elements with @ref annotations

# 3. Act on what you see
bridge.click("@e5")                  # click a button
bridge.fill("@e3", "search query")   # fill a field
bridge.run("press", "Enter")         # press Enter

# 4. Observe again (loop back to step 2)
snap = bridge.snapshot(interactive=True)

# 5. Extract
result = bridge.evaluate("document.querySelector('.result').textContent")
```

---

## iOS Simulator

Requires Xcode + Appium. Pass `-p ios` to use iOS Safari:

```python
bridge = BrowserBridge(extra_args=["-p", "ios"])
bridge.open("https://example.com")
bridge.run("swipe", "up")
bridge.run("tap", "@e1")
bridge.run("-p", "ios", "device", "list")  # list simulators
```

---

## Programmatic API (no CLI)

Import directly — no `cup` CLI required:

```python
from codeupipe.cli.commands.browser_cmds import (
    browser_open, browser_close, browser_snapshot,
    browser_click, browser_fill, browser_eval,
    browser_screenshot, browser_tabs, browser_raw,
    browser_get,
)

result = browser_open("https://example.com", headed=True)
# {"ok": True, "output": "...", "url": "https://example.com"}

snap = browser_snapshot(interactive=True)
# {"ok": True, "output": "...", "snapshot": "- heading ..."}
```

---

## Demo

Run the 11-tier interactive demo:

```bash
python3 examples/browser_demo.py            # headless
python3 examples/browser_demo.py --headed   # watch it happen
```
