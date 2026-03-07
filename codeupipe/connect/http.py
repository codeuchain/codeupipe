"""
HttpConnector — built-in connector Filter for REST APIs.

Uses ``urllib.request`` (stdlib) so it stays zero-dep.  Supports
configurable base URL, HTTP method, headers, and env-var interpolation.
Implements the optional ``health()`` convention.
"""

import json
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

from .config import ConnectorConfig

__all__ = ["HttpConnector"]


class HttpConnector:
    """Built-in HTTP connector Filter.

    Works as a codeupipe Filter (implements ``async call(payload)``).
    Configurable via cup.toml ``[connectors.*]`` with ``provider = "http"``.

    Payload contract:
        Input:  ``path`` (optional, appended to base_url),
                ``body`` (optional dict, sent as JSON for non-GET),
                ``query`` (optional dict, appended as query params).
        Output: ``response`` (parsed JSON body), ``status_code`` (int).
    """

    def __init__(
        self,
        base_url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.method = method.upper()
        self.headers = headers or {}
        self.timeout = timeout

    @classmethod
    def from_config(cls, cfg: ConnectorConfig) -> "HttpConnector":
        """Build an HttpConnector from a ConnectorConfig."""
        base_url = cfg.resolve_env("base_url_env", required=False)
        if base_url is None:
            base_url = cfg.get("base_url", "")
        if not base_url:
            from .config import ConfigError
            raise ConfigError(
                f"Connector '{cfg.name}': HTTP connector requires "
                f"'base_url_env' or 'base_url'"
            )

        method = cfg.get("method", "GET")
        timeout = cfg.get("timeout", 30)

        headers: Dict[str, str] = {}
        raw_headers = cfg.get("headers", {})
        for k, v in raw_headers.items():
            headers[k] = cfg.resolve_interpolated(str(v))

        return cls(base_url=base_url, method=method, headers=headers, timeout=timeout)

    async def call(self, payload: Any) -> Any:
        """Filter protocol — make an HTTP request and return the response."""
        path = payload.get("path", "")
        url = f"{self.base_url}/{path.lstrip('/')}" if path else self.base_url

        body_data = payload.get("body")
        data: Optional[bytes] = None
        if body_data is not None and self.method != "GET":
            data = json.dumps(body_data).encode("utf-8")

        headers = dict(self.headers)
        if data is not None and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url, data=data, headers=headers, method=self.method
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                status = resp.getcode()
                try:
                    parsed = json.loads(resp_body)
                except (json.JSONDecodeError, ValueError):
                    parsed = resp_body
        except urllib.error.HTTPError as e:
            parsed = {"error": str(e), "status_code": e.code}
            status = e.code
        except urllib.error.URLError as e:
            parsed = {"error": str(e.reason)}
            status = 0

        return payload.insert("response", parsed).insert("status_code", status)

    async def health(self) -> bool:
        """Check if the base URL is reachable (HEAD request)."""
        try:
            req = urllib.request.Request(
                self.base_url, method="HEAD", headers=self.headers
            )
            with urllib.request.urlopen(req, timeout=min(self.timeout, 5)):
                return True
        except Exception:
            return False

    def __repr__(self) -> str:
        return f"HttpConnector(base_url={self.base_url!r}, method={self.method!r})"
