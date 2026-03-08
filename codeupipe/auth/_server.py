"""
Local OAuth2 callback server.

Starts a temporary HTTP server on a free port, opens the browser
to the authorization URL, waits for the callback with the auth code,
then shuts down. Pure stdlib — http.server + webbrowser.
"""

import html
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Tuple

__all__ = ["run_oauth_flow"]

_SUCCESS_PAGE = """\
<!DOCTYPE html>
<html>
<head><title>codeupipe — Authenticated</title></head>
<body style="font-family:system-ui;text-align:center;padding:60px;background:#1a1a2e;color:#e0e0e0">
  <h1 style="color:#4ecdc4">&#x2713; Authenticated</h1>
  <p>You can close this tab and return to the terminal.</p>
</body>
</html>
"""

_ERROR_PAGE = """\
<!DOCTYPE html>
<html>
<head><title>codeupipe — Auth Error</title></head>
<body style="font-family:system-ui;text-align:center;padding:60px;background:#1a1a2e;color:#e0e0e0">
  <h1 style="color:#e74c3c">&#x2717; Authentication Failed</h1>
  <p>{error}</p>
</body>
</html>
"""


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth2 callback redirect."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # Extract code and state
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]
        error_desc = params.get("error_description", ["Unknown error"])[0]

        if error:
            self.server._auth_result = ("error", error_desc)  # type: ignore[attr-defined]
            self._send_html(400, _ERROR_PAGE.format(error=html.escape(error_desc)))
        elif code and state == self.server._expected_state:  # type: ignore[attr-defined]
            self.server._auth_result = ("ok", code)  # type: ignore[attr-defined]
            self._send_html(200, _SUCCESS_PAGE)
        else:
            msg = "State mismatch — possible CSRF. Please try again."
            self.server._auth_result = ("error", msg)  # type: ignore[attr-defined]
            self._send_html(400, _ERROR_PAGE.format(error=html.escape(msg)))

        # Signal the main thread to shut down
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _send_html(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        # Suppress noisy request logs
        pass


def run_oauth_flow(
    provider,
    port: int = 0,
    timeout: int = 120,
    open_browser: bool = True,
) -> Tuple[str, str]:
    """Run a complete browser-based OAuth2 flow.

    1. Starts a local HTTP server on *port* (0 = auto-pick free port).
    2. Generates a random state parameter for CSRF protection.
    3. Opens the browser to the provider's authorization URL.
    4. Waits for the callback with the auth code.
    5. Returns (code, redirect_uri) for token exchange.

    Args:
        provider: An AuthProvider instance.
        port: Local port for callback server (0 = auto).
        timeout: Max seconds to wait for the callback.
        open_browser: Whether to auto-open the browser.

    Returns:
        Tuple of (authorization_code, redirect_uri).

    Raises:
        RuntimeError: If the flow fails, times out, or user denies.
        TimeoutError: If the callback is not received in time.
    """
    state = secrets.token_urlsafe(32)

    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    actual_port = server.server_address[1]
    redirect_uri = f"http://localhost:{actual_port}/callback"

    server._expected_state = state  # type: ignore[attr-defined]
    server._auth_result = None  # type: ignore[attr-defined]

    auth_url = provider.authorize_url(redirect_uri, state)

    # Run server in a thread so we can enforce a timeout
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    if open_browser:
        print(f"\nOpening browser for {provider.name} authentication...")
        print(f"If it doesn't open, visit:\n  {auth_url}\n")
        webbrowser.open(auth_url)
    else:
        print(f"\nOpen this URL in your browser:\n  {auth_url}\n")

    # Wait for the callback
    server_thread.join(timeout=timeout)

    # Shut down if still running (timeout)
    server.shutdown()
    server.server_close()

    result = server._auth_result  # type: ignore[attr-defined]
    if result is None:
        raise TimeoutError(
            f"OAuth callback not received within {timeout}s. "
            "Make sure you complete the login in your browser."
        )

    status, value = result
    if status == "error":
        raise RuntimeError(f"OAuth flow failed: {value}")

    return value, redirect_uri
