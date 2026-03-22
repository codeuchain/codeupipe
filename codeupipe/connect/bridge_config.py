"""
BridgeConfig — configuration for localhost / LAN compute bridges.

A bridge connects a browser (or any thin client) to native compute
running on the user's machine or local network.  BridgeConfig describes
*where* the native compute lives and *what* it can do.

Configurable via ``cup.toml`` under ``[bridge]`` or ``[bridge.*]``
sections, environment variables, or programmatic construction.

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "BridgeConfig",
    "BridgeTier",
    "BridgeCapability",
    "load_bridge_configs",
    "BridgeConfigError",
]


class BridgeConfigError(Exception):
    """Raised when bridge configuration is invalid."""


class BridgeCapability:
    """Well-known capability identifiers.

    Capabilities describe what a bridge endpoint can do.  The bridge
    negotiates capabilities at probe time via the health endpoint.
    Custom capabilities are strings — these are just the well-known ones.
    """
    TORCH = "torch"                  # PyTorch available
    CUDA = "cuda"                    # NVIDIA GPU
    MPS = "mps"                      # Apple Metal
    TRANSFORMERS = "transformers"    # HuggingFace Transformers
    DREAM_TRAIN = "dream-train"      # Dream training endpoint
    SWARM = "swarm"                  # Swarm training endpoint
    QUEUE = "queue"                  # Job queue endpoint
    AUTH = "auth"                    # Auth endpoint


class BridgeTier:
    """Compute tier identifiers — ordered by capability.

    The bridge system tries tiers in order: LOCAL → LAN → REMOTE → WASM.
    Higher tiers have more capability but less proximity.
    """
    LOCAL = "local"     # localhost — same machine, native GPU
    LAN = "lan"         # Local network — another machine on same network
    REMOTE = "remote"   # Internet — cloud server, VPS, etc.
    WASM = "wasm"       # Browser-only — WebAssembly fallback

    ORDER = [LOCAL, LAN, REMOTE, WASM]

    @classmethod
    def rank(cls, tier: str) -> int:
        """Return the preference rank (lower = preferred)."""
        try:
            return cls.ORDER.index(tier)
        except ValueError:
            return len(cls.ORDER)


@dataclass
class BridgeConfig:
    """Configuration for a single bridge endpoint.

    Attributes:
        name: Human-readable name (e.g. 'my-gpu', 'macbook-pro').
        tier: Compute tier (local, lan, remote, wasm).
        host: Hostname or IP address.
        port: Port number.
        health_path: Path for health check endpoint.
        secret: Shared secret for authentication (optional).
        capabilities: List of required capabilities.
        probe_timeout: Timeout for health probe in seconds.
        auto_start: Command to auto-start the bridge service.
        auto_start_args: Arguments for auto-start command.
        headers: Extra HTTP headers for all requests.
        env_prefix: Prefix for environment variable overrides.
        metadata: Arbitrary key-value metadata.
    """
    name: str = "default"
    tier: str = BridgeTier.LOCAL
    host: str = "localhost"
    port: int = 8089
    health_path: str = "/health"
    secret: str = ""
    capabilities: List[str] = field(default_factory=list)
    probe_timeout: float = 3.0
    auto_start: str = ""
    auto_start_args: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    env_prefix: str = "BRIDGE"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        """Compute the base URL from host + port."""
        scheme = "https" if self.port == 443 else "http"
        if self.host in ("localhost", "127.0.0.1", "::1"):
            scheme = "http"
        return f"{scheme}://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        """Full URL for the health check endpoint."""
        return f"{self.base_url}{self.health_path}"

    def with_overrides(self, **kwargs: Any) -> "BridgeConfig":
        """Return a new BridgeConfig with the given fields overridden."""
        current = {
            "name": self.name,
            "tier": self.tier,
            "host": self.host,
            "port": self.port,
            "health_path": self.health_path,
            "secret": self.secret,
            "capabilities": list(self.capabilities),
            "probe_timeout": self.probe_timeout,
            "auto_start": self.auto_start,
            "auto_start_args": list(self.auto_start_args),
            "headers": dict(self.headers),
            "env_prefix": self.env_prefix,
            "metadata": dict(self.metadata),
        }
        current.update(kwargs)
        return BridgeConfig(**current)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], name: str = "default") -> "BridgeConfig":
        """Build a BridgeConfig from a dict (e.g. parsed from cup.toml)."""
        return cls(
            name=data.get("name", name),
            tier=data.get("tier", BridgeTier.LOCAL),
            host=data.get("host", "localhost"),
            port=int(data.get("port", 8089)),
            health_path=data.get("health_path", "/health"),
            secret=data.get("secret", ""),
            capabilities=data.get("capabilities", []),
            probe_timeout=float(data.get("probe_timeout", 3.0)),
            auto_start=data.get("auto_start", ""),
            auto_start_args=data.get("auto_start_args", []),
            headers=data.get("headers", {}),
            env_prefix=data.get("env_prefix", "BRIDGE"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_env(cls, prefix: str = "BRIDGE", name: str = "default") -> "BridgeConfig":
        """Build a BridgeConfig from environment variables.

        Reads: {PREFIX}_HOST, {PREFIX}_PORT, {PREFIX}_SECRET,
        {PREFIX}_HEALTH_PATH, {PREFIX}_TIER, {PREFIX}_AUTO_START.
        """
        p = prefix.upper()
        return cls(
            name=os.environ.get(f"{p}_NAME", name),
            tier=os.environ.get(f"{p}_TIER", BridgeTier.LOCAL),
            host=os.environ.get(f"{p}_HOST", "localhost"),
            port=int(os.environ.get(f"{p}_PORT", "8089")),
            health_path=os.environ.get(f"{p}_HEALTH_PATH", "/health"),
            secret=os.environ.get(f"{p}_SECRET", ""),
            probe_timeout=float(os.environ.get(f"{p}_PROBE_TIMEOUT", "3.0")),
            auto_start=os.environ.get(f"{p}_AUTO_START", ""),
            env_prefix=prefix,
        )

    @classmethod
    def from_url(cls, url: str, name: str = "default") -> "BridgeConfig":
        """Build a BridgeConfig from a URL string.

        Example: BridgeConfig.from_url("http://localhost:8089")
        """
        # stdlib parse
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 8089)
        tier = BridgeTier.LOCAL if host in ("localhost", "127.0.0.1", "::1") else BridgeTier.REMOTE
        return cls(name=name, tier=tier, host=host, port=port)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dict (for JSON, TOML, etc.)."""
        return {
            "name": self.name,
            "tier": self.tier,
            "host": self.host,
            "port": self.port,
            "health_path": self.health_path,
            "secret": self.secret,
            "capabilities": self.capabilities,
            "probe_timeout": self.probe_timeout,
            "auto_start": self.auto_start,
            "auto_start_args": self.auto_start_args,
            "headers": self.headers,
            "env_prefix": self.env_prefix,
            "metadata": self.metadata,
        }


def load_bridge_configs(
    raw: Dict[str, Any],
) -> List[BridgeConfig]:
    """Parse bridge configs from a dict (typically from cup.toml [bridge.*]).

    Supports two forms:
        1. Single bridge:   [bridge] with host/port/etc.
        2. Multiple bridges: [bridge.gpu1], [bridge.laptop], etc.

    Returns a list of BridgeConfig sorted by tier preference.
    """
    configs = []

    # Check if this is a single bridge config (has 'host' or 'port' at top level)
    if "host" in raw or "port" in raw or "tier" in raw:
        configs.append(BridgeConfig.from_dict(raw))
    else:
        # Multiple named bridges
        for name, section in raw.items():
            if isinstance(section, dict):
                configs.append(BridgeConfig.from_dict(section, name=name))

    # Sort by tier preference (local first)
    configs.sort(key=lambda c: BridgeTier.rank(c.tier))
    return configs
