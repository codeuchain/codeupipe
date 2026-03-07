"""
RemoteFilter: Execute filter logic on a remote HTTP endpoint.

Same Filter interface — pipelines don't know the difference.
Uses stdlib urllib to maintain zero-dependency constraint.
"""

import asyncio
import urllib.request
from typing import Any, Dict, Optional

from ..core.payload import Payload

__all__ = ["RemoteFilter"]


class RemoteFilter:
    """A Filter that sends payloads to a remote HTTP endpoint.

    The remote service receives a serialized Payload (JSON POST),
    processes it, and returns a serialized Payload as the response.

    Usage:
        remote = RemoteFilter("http://my-service:8080/process")
        pipeline.add_filter(remote, name="remote_step")
    """

    def __init__(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ):
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout

    async def call(self, payload: Payload) -> Payload:
        """Send payload to remote endpoint and return the response."""
        data = payload.serialize()
        loop = asyncio.get_running_loop()
        response_data = await loop.run_in_executor(
            None, self._send, data
        )
        return Payload.deserialize(response_data)

    def _send(self, data: bytes) -> bytes:
        """Blocking HTTP POST — runs in executor for async compat."""
        req = urllib.request.Request(
            self._url,
            data=data,
            headers={"Content-Type": "application/json", **self._headers},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read()
