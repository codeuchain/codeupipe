"""
LocalBridge — generic browser↔desktop bridge for native compute.

The bridge is a Filter that auto-discovers local (or LAN/remote) native
compute endpoints, negotiates capabilities, and delegates work to the
best available tier.  When no native compute is available, the bridge
reports the gap so the caller can fall back to browser-only WASM.

Architecture
------------

    Browser (thin client)
       │
       ├─ Tier 1: localhost:8089  ← native GPU, PyTorch, full power
       ├─ Tier 2: LAN host       ← another machine on same network
       ├─ Tier 3: Remote server   ← cloud GPU
       └─ Tier 4: WASM fallback   ← browser-only, zero install

The bridge probes endpoints in tier order and connects to the first
one that is alive and has the required capabilities.

Usage (Python — as a CUP Filter)::

    from codeupipe.connect import LocalBridge, BridgeConfig

    bridge = LocalBridge(BridgeConfig(port=8089))
    await bridge.connect()

    if bridge.is_alive:
        result = await bridge.call(payload)

Usage (JavaScript — see bridge.js)::

    const bridge = new Bridge({port: 8089});
    await bridge.probe();
    if (bridge.alive) {
        const result = await bridge.delegate('/dream-train', data);
    }

Stdlib only — uses urllib for HTTP.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .bridge_config import BridgeConfig, BridgeTier, BridgeConfigError

__all__ = [
    "LocalBridge",
    "BridgeEndpoint",
    "BridgeError",
]


class BridgeError(Exception):
    """Raised when a bridge operation fails."""


@dataclass
class BridgeEndpoint:
    """A discovered and probed compute endpoint.

    This is the runtime representation of a bridge — config + live state.
    """
    config: BridgeConfig
    alive: bool = False
    latency_ms: float = 0.0
    capabilities: List[str] = field(default_factory=list)
    device: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_probe: float = 0.0
    error: str = ""

    @property
    def tier(self) -> str:
        return self.config.tier

    @property
    def base_url(self) -> str:
        return self.config.base_url

    def has_capability(self, cap: str) -> bool:
        """Check if this endpoint has a specific capability."""
        return cap in self.capabilities

    def has_all(self, caps: Sequence[str]) -> bool:
        """Check if this endpoint has ALL of the given capabilities."""
        return all(cap in self.capabilities for cap in caps)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON / dashboard display."""
        return {
            "name": self.config.name,
            "tier": self.tier,
            "alive": self.alive,
            "base_url": self.base_url,
            "device": self.device,
            "capabilities": self.capabilities,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
        }


class LocalBridge:
    """Generic bridge from browser/client to native compute.

    Implements the codeupipe Filter protocol (``async call(payload)``)
    so it can be dropped into any pipeline.  Also provides lower-level
    ``probe``, ``request``, and ``delegate`` methods for direct use.

    The bridge manages multiple endpoints and selects the best one
    based on tier preference, capabilities, and liveness.

    Parameters
    ----------
    configs : BridgeConfig or list of BridgeConfig
        One or more endpoint configurations to try.
    required_capabilities : list of str
        Capabilities the endpoint MUST have.  Endpoints without all
        of these are filtered out during selection.
    auto_probe : bool
        Probe endpoints on first ``call()`` if not already probed.
    delegate_path : str
        Default path for ``call()`` delegation (e.g. '/dream-train').
    """

    def __init__(
        self,
        configs: "BridgeConfig | List[BridgeConfig] | None" = None,
        required_capabilities: Optional[List[str]] = None,
        auto_probe: bool = True,
        delegate_path: str = "/health",
    ) -> None:
        if configs is None:
            configs = [BridgeConfig()]
        elif isinstance(configs, BridgeConfig):
            configs = [configs]
        self._configs = list(configs)
        self._required = required_capabilities or []
        self._auto_probe = auto_probe
        self._delegate_path = delegate_path

        self._endpoints: List[BridgeEndpoint] = []
        self._active: Optional[BridgeEndpoint] = None
        self._probed = False

    # ── Properties ───────────────────────────────────────────────────

    @property
    def is_alive(self) -> bool:
        """Whether we have an active, alive endpoint."""
        return self._active is not None and self._active.alive

    @property
    def active_endpoint(self) -> Optional[BridgeEndpoint]:
        """The currently selected endpoint (or None)."""
        return self._active

    @property
    def endpoints(self) -> List[BridgeEndpoint]:
        """All discovered endpoints."""
        return list(self._endpoints)

    @property
    def tier(self) -> str:
        """The tier of the active endpoint, or 'wasm' if none."""
        if self._active and self._active.alive:
            return self._active.tier
        return BridgeTier.WASM

    @property
    def capabilities(self) -> List[str]:
        """Capabilities of the active endpoint."""
        if self._active:
            return list(self._active.capabilities)
        return []

    @property
    def device(self) -> str:
        """Device of the active endpoint (cuda, mps, cpu, wasm)."""
        if self._active and self._active.alive:
            return self._active.device
        return "wasm"

    # ── Probe & Connect ──────────────────────────────────────────────

    def probe_sync(self) -> List[BridgeEndpoint]:
        """Probe all configured endpoints synchronously.

        Returns the list of endpoints with their alive/capability status.
        Sets the active endpoint to the best available one.
        """
        self._endpoints = []

        for config in self._configs:
            endpoint = self._probe_one(config)
            self._endpoints.append(endpoint)

        self._select_active()
        self._probed = True
        return list(self._endpoints)

    async def probe(self) -> List[BridgeEndpoint]:
        """Probe all configured endpoints (async wrapper).

        Runs probes concurrently for speed.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.probe_sync)

    async def connect(self) -> bool:
        """Probe and connect to the best available endpoint.

        Returns True if a live endpoint was found.
        """
        await self.probe()
        return self.is_alive

    def _probe_one(self, config: BridgeConfig) -> BridgeEndpoint:
        """Probe a single endpoint by hitting its health URL."""
        endpoint = BridgeEndpoint(config=config)

        try:
            t0 = time.monotonic()

            req = urllib.request.Request(
                config.health_url,
                method="GET",
                headers={"Accept": "application/json", **config.headers},
            )
            if config.secret:
                req.add_header("X-Spore-Secret", config.secret)

            with urllib.request.urlopen(req, timeout=config.probe_timeout) as resp:
                body = resp.read().decode("utf-8")
                latency = (time.monotonic() - t0) * 1000

            endpoint.latency_ms = latency
            endpoint.last_probe = time.time()

            # Parse health response
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                data = {}

            endpoint.alive = data.get("status") == "alive" or resp.getcode() == 200
            endpoint.device = data.get("device", "unknown")
            endpoint.metadata = data

            # Extract capabilities from health response
            caps = []
            if data.get("torch_version"):
                caps.append("torch")
            if data.get("cuda"):
                caps.append("cuda")
            if data.get("mps"):
                caps.append("mps")
            if data.get("swarm") is not None:
                caps.append("swarm")
            if data.get("queue") is not None:
                caps.append("queue")
            # Check for explicit capabilities list
            if isinstance(data.get("capabilities"), list):
                caps.extend(data["capabilities"])
            endpoint.capabilities = sorted(set(caps))

        except urllib.error.URLError as e:
            endpoint.alive = False
            endpoint.error = str(e.reason) if hasattr(e, "reason") else str(e)
        except Exception as e:
            endpoint.alive = False
            endpoint.error = str(e)

        return endpoint

    def _select_active(self) -> None:
        """Select the best endpoint from probed results.

        Priority: alive + has required capabilities + lowest tier rank.
        Within same tier, prefer lower latency.
        """
        candidates = []
        for ep in self._endpoints:
            if not ep.alive:
                continue
            if self._required and not ep.has_all(self._required):
                continue
            candidates.append(ep)

        if not candidates:
            self._active = None
            return

        # Sort by: tier rank (ascending), then latency (ascending)
        candidates.sort(key=lambda ep: (
            BridgeTier.rank(ep.tier),
            ep.latency_ms,
        ))
        self._active = candidates[0]

    # ── Request / Delegate ───────────────────────────────────────────

    def request_sync(
        self,
        path: str,
        method: str = "GET",
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        endpoint: Optional[BridgeEndpoint] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to the active (or specified) endpoint.

        Returns the parsed JSON response, or raises BridgeError.
        """
        ep = endpoint or self._active
        if ep is None or not ep.alive:
            raise BridgeError("No active bridge endpoint")

        url = f"{ep.base_url}{path}"
        req_headers = {
            "Accept": "application/json",
            **ep.config.headers,
        }
        if ep.config.secret:
            req_headers["X-Spore-Secret"] = ep.config.secret
        if headers:
            req_headers.update(headers)

        data_bytes = None
        if body is not None:
            data_bytes = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers=req_headers,
            method=method,
        )

        try:
            t = timeout or ep.config.probe_timeout * 10  # longer for real work
            with urllib.request.urlopen(req, timeout=t) as resp:
                resp_body = resp.read().decode("utf-8")
                try:
                    return json.loads(resp_body)
                except (json.JSONDecodeError, ValueError):
                    return {"raw": resp_body, "status_code": resp.getcode()}
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
            except Exception:
                err_body = {"error": str(e)}
            raise BridgeError(
                f"Bridge request failed: {e.code} {url}: {err_body}"
            )
        except urllib.error.URLError as e:
            ep.alive = False
            raise BridgeError(f"Bridge connection lost: {e}")

    async def request(
        self,
        path: str,
        method: str = "GET",
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Async wrapper for request_sync."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.request_sync(path, method, body, headers, timeout),
        )

    async def delegate(
        self,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Delegate work to the active bridge endpoint (POST).

        This is the main API for sending work to native compute.
        """
        return await self.request(path, method="POST", body=body, timeout=timeout)

    # ── CUP Filter Protocol ─────────────────────────────────────────

    async def call(self, payload: Any) -> Any:
        """Filter protocol — delegate payload to bridge endpoint.

        Reads 'bridge_path' from payload (or uses default delegate_path).
        Reads 'bridge_body' from payload (or serializes the full payload).
        Returns payload with 'bridge_response' and 'bridge_tier' added.
        """
        if not self._probed and self._auto_probe:
            await self.probe()

        bridge_path = payload.get("bridge_path", self._delegate_path)
        bridge_body = payload.get("bridge_body", None)

        if self.is_alive:
            try:
                response = await self.delegate(bridge_path, body=bridge_body)
                return (
                    payload
                    .insert("bridge_response", response)
                    .insert("bridge_tier", self.tier)
                    .insert("bridge_device", self.device)
                    .insert("bridge_alive", True)
                )
            except BridgeError as e:
                return (
                    payload
                    .insert("bridge_response", {"error": str(e)})
                    .insert("bridge_tier", BridgeTier.WASM)
                    .insert("bridge_device", "wasm")
                    .insert("bridge_alive", False)
                    .insert("bridge_error", str(e))
                )
        else:
            return (
                payload
                .insert("bridge_response", None)
                .insert("bridge_tier", BridgeTier.WASM)
                .insert("bridge_device", "wasm")
                .insert("bridge_alive", False)
            )

    # ── Status / Introspection ───────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Return full bridge status for dashboards/logging."""
        return {
            "active": self._active.to_dict() if self._active else None,
            "tier": self.tier,
            "device": self.device,
            "is_alive": self.is_alive,
            "probed": self._probed,
            "endpoints": [ep.to_dict() for ep in self._endpoints],
            "required_capabilities": self._required,
        }

    def __repr__(self) -> str:
        state = "alive" if self.is_alive else "disconnected"
        tier = self.tier
        device = self.device
        return f"LocalBridge({state}, tier={tier}, device={device})"
