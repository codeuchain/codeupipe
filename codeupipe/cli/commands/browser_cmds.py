"""``cup browser`` subcommands — programmatic browser control via agent-browser.

Wraps the ``codeupipe.browser`` Filter layer through CLI subcommands.
Each subcommand builds a one-shot Pipeline: open, close, snapshot,
click, fill, eval, screenshot, tabs, raw, get.
"""

import json
import sys

from codeupipe import Payload, Pipeline


# ── Programmatic API (importable without CLI) ───────────────────────

def browser_open(url, *, headed=False, cdp_port=None, profile=None):
    """Open a URL in a headless browser.

    Returns a dict with ``ok``, ``output``, and ``url`` keys.
    """
    from codeupipe.browser import BrowserBridge, BrowserOpen

    bridge = BrowserBridge(headed=headed, cdp_port=cdp_port, profile=profile)
    filt = BrowserOpen(bridge=bridge, url=url)
    pipeline = Pipeline()
    pipeline.add_filter(filt)
    result = pipeline.run(Payload())
    return {
        "ok": result.get("browser_ok", False),
        "output": result.get("browser_output", ""),
        "url": result.get("browser_url", url),
    }


def browser_close(*, headed=False, cdp_port=None, profile=None):
    """Close the browser session.

    Returns a dict with ``ok`` and ``output`` keys.
    """
    from codeupipe.browser import BrowserBridge, BrowserClose

    bridge = BrowserBridge(headed=headed, cdp_port=cdp_port, profile=profile)
    filt = BrowserClose(bridge=bridge)
    pipeline = Pipeline()
    pipeline.add_filter(filt)
    result = pipeline.run(Payload())
    return {
        "ok": result.get("browser_ok", False),
        "output": result.get("browser_output", ""),
    }


def browser_snapshot(*, interactive=True, headed=False, cdp_port=None, profile=None):
    """Take an accessibility-tree snapshot of the current page.

    Returns a dict with ``ok``, ``output``, and ``snapshot`` keys.
    """
    from codeupipe.browser import BrowserBridge, BrowserSnapshot

    bridge = BrowserBridge(headed=headed, cdp_port=cdp_port, profile=profile)
    filt = BrowserSnapshot(bridge=bridge)
    payload = Payload({"browser_interactive": interactive})
    pipeline = Pipeline()
    pipeline.add_filter(filt)
    result = pipeline.run(payload)
    return {
        "ok": result.get("browser_ok", False),
        "output": result.get("browser_output", ""),
        "snapshot": result.get("browser_snapshot", ""),
    }


def browser_click(selector, *, headed=False, cdp_port=None, profile=None):
    """Click an element by its ``@ref`` selector.

    Returns a dict with ``ok`` and ``output`` keys.
    """
    from codeupipe.browser import BrowserBridge, BrowserClick

    bridge = BrowserBridge(headed=headed, cdp_port=cdp_port, profile=profile)
    filt = BrowserClick(bridge=bridge, selector=selector)
    pipeline = Pipeline()
    pipeline.add_filter(filt)
    result = pipeline.run(Payload())
    return {
        "ok": result.get("browser_ok", False),
        "output": result.get("browser_output", ""),
    }


def browser_fill(selector, text, *, headed=False, cdp_port=None, profile=None):
    """Fill a form field identified by ``@ref`` selector with text.

    Returns a dict with ``ok`` and ``output`` keys.
    """
    from codeupipe.browser import BrowserBridge, BrowserFill

    bridge = BrowserBridge(headed=headed, cdp_port=cdp_port, profile=profile)
    filt = BrowserFill(bridge=bridge, selector=selector, text=text)
    pipeline = Pipeline()
    pipeline.add_filter(filt)
    result = pipeline.run(Payload())
    return {
        "ok": result.get("browser_ok", False),
        "output": result.get("browser_output", ""),
    }


def browser_eval(expression, *, headed=False, cdp_port=None, profile=None):
    """Evaluate a JavaScript expression in the current page context.

    Returns a dict with ``ok``, ``output``, and ``result`` keys.
    """
    from codeupipe.browser import BrowserBridge, BrowserEval

    bridge = BrowserBridge(headed=headed, cdp_port=cdp_port, profile=profile)
    filt = BrowserEval(bridge=bridge, expression=expression)
    pipeline = Pipeline()
    pipeline.add_filter(filt)
    result = pipeline.run(Payload())
    return {
        "ok": result.get("browser_ok", False),
        "output": result.get("browser_output", ""),
        "result": result.get("browser_eval", ""),
    }


def browser_screenshot(path=None, *, headed=False, cdp_port=None, profile=None):
    """Take a screenshot of the current page.

    Returns a dict with ``ok``, ``output``, and ``path`` keys.
    """
    from codeupipe.browser import BrowserBridge, BrowserScreenshot

    bridge = BrowserBridge(headed=headed, cdp_port=cdp_port, profile=profile)
    filt = BrowserScreenshot(bridge=bridge, path=path)
    pipeline = Pipeline()
    pipeline.add_filter(filt)
    result = pipeline.run(Payload())
    return {
        "ok": result.get("browser_ok", False),
        "output": result.get("browser_output", ""),
        "path": result.get("browser_screenshot", ""),
    }


def browser_tabs(*, headed=False, cdp_port=None, profile=None):
    """List open browser tabs.

    Returns a dict with ``ok``, ``output``, and ``tabs`` keys.
    """
    from codeupipe.browser import BrowserBridge, BrowserTabs

    bridge = BrowserBridge(headed=headed, cdp_port=cdp_port, profile=profile)
    filt = BrowserTabs(bridge=bridge)
    pipeline = Pipeline()
    pipeline.add_filter(filt)
    result = pipeline.run(Payload())
    return {
        "ok": result.get("browser_ok", False),
        "output": result.get("browser_output", ""),
        "tabs": result.get("browser_tabs", ""),
    }


def browser_raw(method, params=None, *, headed=False, cdp_port=None, profile=None):
    """Send a raw CDP method to the browser.

    Returns a dict with ``ok``, ``output``, and ``raw`` keys.
    """
    from codeupipe.browser import BrowserBridge, BrowserRaw

    bridge = BrowserBridge(headed=headed, cdp_port=cdp_port, profile=profile)
    filt = BrowserRaw(bridge=bridge)
    payload_data = {"browser_cdp_method": method}
    if params:
        payload_data["browser_cdp_params"] = params
    pipeline = Pipeline()
    pipeline.add_filter(filt)
    result = pipeline.run(Payload(payload_data))
    return {
        "ok": result.get("browser_ok", False),
        "output": result.get("browser_output", ""),
        "raw": result.get("browser_raw", ""),
    }


def browser_get(what, selector=None, *, headed=False, cdp_port=None, profile=None):
    """Get a property from the current page (text, title, url, html, value).

    Returns a dict with ``ok``, ``output``, and ``result`` keys.
    """
    from codeupipe.browser import BrowserBridge, BrowserGet

    bridge = BrowserBridge(headed=headed, cdp_port=cdp_port, profile=profile)
    filt = BrowserGet(bridge=bridge)
    payload_data = {"browser_get_what": what}
    if selector:
        payload_data["browser_get_selector"] = selector
    pipeline = Pipeline()
    pipeline.add_filter(filt)
    result = pipeline.run(Payload(payload_data))
    return {
        "ok": result.get("browser_ok", False),
        "output": result.get("browser_output", ""),
        "result": result.get("browser_get_result", ""),
    }


# ── Shared Bridge Options ──────────────────────────────────────────

def _add_bridge_args(parser):
    """Add common bridge flags to a subparser."""
    parser.add_argument(
        "--headed", action="store_true", default=False,
        help="Run browser in headed (visible) mode",
    )
    parser.add_argument(
        "--cdp-port", type=int, default=None, dest="cdp_port",
        help="Connect to existing browser via CDP port",
    )
    parser.add_argument(
        "--profile", default=None,
        help="Named browser profile for persistent sessions",
    )


def _bridge_kwargs(args):
    """Extract bridge keyword arguments from parsed args."""
    return {
        "headed": getattr(args, "headed", False),
        "cdp_port": getattr(args, "cdp_port", None),
        "profile": getattr(args, "profile", None),
    }


# ── Parser Setup ────────────────────────────────────────────────────

def setup(sub, reg):
    # cup browser open <url>
    open_p = sub.add_parser("browser-open", help="Open a URL in headless browser")
    open_p.add_argument("url", help="URL to navigate to")
    _add_bridge_args(open_p)
    reg.register("browser-open", _handle_open)

    # cup browser close
    close_p = sub.add_parser("browser-close", help="Close the browser session")
    _add_bridge_args(close_p)
    reg.register("browser-close", _handle_close)

    # cup browser snapshot [--no-interactive]
    snap_p = sub.add_parser(
        "browser-snapshot",
        help="Take an accessibility-tree snapshot of the current page",
    )
    snap_p.add_argument(
        "--no-interactive", action="store_true", default=False,
        dest="no_interactive",
        help="Omit interactive @ref annotations from snapshot",
    )
    _add_bridge_args(snap_p)
    reg.register("browser-snapshot", _handle_snapshot)

    # cup browser click <selector>
    click_p = sub.add_parser("browser-click", help="Click an element by @ref selector")
    click_p.add_argument("selector", help="Element selector (e.g. @e2)")
    _add_bridge_args(click_p)
    reg.register("browser-click", _handle_click)

    # cup browser fill <selector> <text>
    fill_p = sub.add_parser("browser-fill", help="Fill a form field with text")
    fill_p.add_argument("selector", help="Element selector (e.g. @e3)")
    fill_p.add_argument("text", help="Text to fill into the field")
    _add_bridge_args(fill_p)
    reg.register("browser-fill", _handle_fill)

    # cup browser eval <expression>
    eval_p = sub.add_parser("browser-eval", help="Evaluate JavaScript in the page")
    eval_p.add_argument("expression", help="JavaScript expression to evaluate")
    _add_bridge_args(eval_p)
    reg.register("browser-eval", _handle_eval)

    # cup browser screenshot [path]
    ss_p = sub.add_parser("browser-screenshot", help="Take a screenshot of the current page")
    ss_p.add_argument("path", nargs="?", default=None, help="Output path (default: auto-generated)")
    _add_bridge_args(ss_p)
    reg.register("browser-screenshot", _handle_screenshot)

    # cup browser tabs
    tabs_p = sub.add_parser("browser-tabs", help="List open browser tabs")
    _add_bridge_args(tabs_p)
    reg.register("browser-tabs", _handle_tabs)

    # cup browser raw <method> [params-json]
    raw_p = sub.add_parser(
        "browser-raw",
        help="Send a raw CDP method to the browser",
    )
    raw_p.add_argument("method", help="CDP method name (e.g. Page.getNavigationHistory)")
    raw_p.add_argument(
        "params_json", nargs="?", default=None,
        help="JSON-encoded parameters (e.g. '{\"depth\": -1}')",
    )
    _add_bridge_args(raw_p)
    reg.register("browser-raw", _handle_raw)

    # cup browser get <what> [selector]
    get_p = sub.add_parser(
        "browser-get",
        help="Get a page property (text, title, url, html, value)",
    )
    get_p.add_argument("what", choices=["text", "title", "url", "html", "value"],
                       help="What to retrieve")
    get_p.add_argument("selector", nargs="?", default=None,
                       help="Optional @ref selector for text/value/html")
    _add_bridge_args(get_p)
    reg.register("browser-get", _handle_get)


# ── Handlers ────────────────────────────────────────────────────────

def _handle_open(args):
    try:
        result = browser_open(args.url, **_bridge_kwargs(args))
        if result["ok"]:
            print(f"✓ Opened {result['url']}")
            if result["output"]:
                print(f"  {result['output']}")
            return 0
        else:
            print(f"✗ Failed to open {args.url}", file=sys.stderr)
            if result["output"]:
                print(f"  {result['output']}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_close(args):
    try:
        result = browser_close(**_bridge_kwargs(args))
        if result["ok"]:
            print("✓ Browser closed")
            return 0
        else:
            print("✗ Failed to close browser", file=sys.stderr)
            if result["output"]:
                print(f"  {result['output']}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_snapshot(args):
    try:
        interactive = not getattr(args, "no_interactive", False)
        result = browser_snapshot(
            interactive=interactive, **_bridge_kwargs(args),
        )
        if result["ok"]:
            print(result["snapshot"])
            return 0
        else:
            print("✗ Failed to take snapshot", file=sys.stderr)
            if result["output"]:
                print(f"  {result['output']}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_click(args):
    try:
        result = browser_click(args.selector, **_bridge_kwargs(args))
        if result["ok"]:
            print(f"✓ Clicked {args.selector}")
            return 0
        else:
            print(f"✗ Failed to click {args.selector}", file=sys.stderr)
            if result["output"]:
                print(f"  {result['output']}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_fill(args):
    try:
        result = browser_fill(args.selector, args.text, **_bridge_kwargs(args))
        if result["ok"]:
            print(f"✓ Filled {args.selector}")
            return 0
        else:
            print(f"✗ Failed to fill {args.selector}", file=sys.stderr)
            if result["output"]:
                print(f"  {result['output']}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_eval(args):
    try:
        result = browser_eval(args.expression, **_bridge_kwargs(args))
        if result["ok"]:
            print(result["result"])
            return 0
        else:
            print("✗ Failed to evaluate expression", file=sys.stderr)
            if result["output"]:
                print(f"  {result['output']}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_screenshot(args):
    try:
        result = browser_screenshot(
            path=getattr(args, "path", None), **_bridge_kwargs(args),
        )
        if result["ok"]:
            print(f"✓ Screenshot saved to {result['path']}")
            return 0
        else:
            print("✗ Failed to take screenshot", file=sys.stderr)
            if result["output"]:
                print(f"  {result['output']}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_tabs(args):
    try:
        result = browser_tabs(**_bridge_kwargs(args))
        if result["ok"]:
            print(result["tabs"])
            return 0
        else:
            print("✗ Failed to list tabs", file=sys.stderr)
            if result["output"]:
                print(f"  {result['output']}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_raw(args):
    try:
        params = None
        if args.params_json:
            try:
                params = json.loads(args.params_json)
            except json.JSONDecodeError as je:
                print(f"Error: invalid JSON params — {je}", file=sys.stderr)
                return 1
        result = browser_raw(args.method, params=params, **_bridge_kwargs(args))
        if result["ok"]:
            print(result["raw"])
            return 0
        else:
            print(f"✗ Failed to send {args.method}", file=sys.stderr)
            if result["output"]:
                print(f"  {result['output']}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_get(args):
    try:
        result = browser_get(
            args.what,
            selector=getattr(args, "selector", None),
            **_bridge_kwargs(args),
        )
        if result["ok"]:
            print(result["result"])
            return 0
        else:
            print(f"✗ Failed to get {args.what}", file=sys.stderr)
            if result["output"]:
                print(f"  {result['output']}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
