"""
Bridge discovery — find native compute endpoints automatically.

Scans localhost well-known ports, optional LAN broadcast, and returns
a list of live BridgeEndpoints.  Used by dashboards and CLI tools to
auto-detect compute without manual configuration.

Discovery methods:
    1. Localhost port scan — try well-known ports (8089, 8090, 8091, ...)
    2. LAN UDP broadcast  — send a discovery beacon, listen for responses
    3. Explicit list       — probe a list of host:port pairs

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Sequence

from .bridge_config import BridgeConfig, BridgeTier
from .local_bridge import BridgeEndpoint, LocalBridge

__all__ = [
    "discover_bridges",
    "scan_localhost",
    "scan_lan",
    "DEFAULT_PORTS",
    "DISCOVERY_PORT",
]

# Well-known ports for spore runners and compute bridges
DEFAULT_PORTS = [8089, 8090, 8091, 8092, 8080, 9090, 5000]

# UDP port for LAN discovery beacons
DISCOVERY_PORT = 41890


def discover_bridges(
    ports: Optional[List[int]] = None,
    scan_local: bool = True,
    scan_network: bool = False,
    extra_hosts: Optional[List[str]] = None,
    health_path: str = "/health",
    timeout: float = 2.0,
    required_capabilities: Optional[List[str]] = None,
) -> LocalBridge:
    """Discover compute bridges and return a configured LocalBridge.

    This is the main entry point for auto-discovery.  It scans
    localhost, optionally the LAN, and any extra hosts, then returns
    a LocalBridge pre-configured with all discovered endpoints.

    Args:
        ports: Ports to scan on localhost (default: DEFAULT_PORTS).
        scan_local: Whether to scan localhost ports.
        scan_network: Whether to do LAN UDP discovery.
        extra_hosts: Additional host:port strings to probe.
        health_path: Health endpoint path.
        timeout: Per-probe timeout in seconds.
        required_capabilities: Required capabilities filter.

    Returns:
        A LocalBridge with all discovered endpoints, probed and ready.
    """
    configs = []

    if scan_local:
        local_configs = scan_localhost(
            ports=ports or DEFAULT_PORTS,
            health_path=health_path,
            timeout=timeout,
        )
        configs.extend(local_configs)

    if scan_network:
        lan_configs = scan_lan(timeout=timeout)
        configs.extend(lan_configs)

    if extra_hosts:
        for host_str in extra_hosts:
            config = _parse_host_string(host_str, health_path)
            configs.append(config)

    if not configs:
        # Nothing to scan — return an empty bridge
        configs = [BridgeConfig(name="default", port=8089)]

    bridge = LocalBridge(
        configs=configs,
        required_capabilities=required_capabilities,
        auto_probe=False,
    )
    bridge.probe_sync()
    return bridge


def scan_localhost(
    ports: Optional[List[int]] = None,
    health_path: str = "/health",
    timeout: float = 1.0,
) -> List[BridgeConfig]:
    """Scan localhost for live compute endpoints.

    Does a quick TCP connect check before HTTP probe to avoid
    slow timeouts on closed ports.

    Returns BridgeConfig for each port that has something listening.
    """
    if ports is None:
        ports = DEFAULT_PORTS

    configs = []
    for port in ports:
        if _tcp_open("127.0.0.1", port, timeout=min(timeout, 0.5)):
            configs.append(BridgeConfig(
                name=f"local-{port}",
                tier=BridgeTier.LOCAL,
                host="127.0.0.1",
                port=port,
                health_path=health_path,
                probe_timeout=timeout,
            ))

    return configs


def scan_lan(
    timeout: float = 2.0,
    broadcast_port: int = DISCOVERY_PORT,
) -> List[BridgeConfig]:
    """Discover compute bridges on the local network via UDP broadcast.

    Sends a JSON discovery beacon and listens for responses.
    Each response contains the responder's host, port, and capabilities.

    Protocol:
        → UDP broadcast to 255.255.255.255:41890
          {"type": "bridge-discover", "version": 1}

        ← UDP response from each bridge:
          {"type": "bridge-announce", "version": 1,
           "host": "192.168.1.42", "port": 8089,
           "name": "my-gpu", "capabilities": ["torch", "cuda"]}

    Returns BridgeConfig for each responder.
    """
    configs = []

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)

        beacon = json.dumps({
            "type": "bridge-discover",
            "version": 1,
        }).encode("utf-8")

        sock.sendto(beacon, ("255.255.255.255", broadcast_port))

        # Collect responses until timeout
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                remaining = max(0.1, deadline - time.monotonic())
                sock.settimeout(remaining)
                data, addr = sock.recvfrom(4096)

                response = json.loads(data.decode("utf-8"))
                if response.get("type") != "bridge-announce":
                    continue

                host = response.get("host", addr[0])
                port = response.get("port", 8089)
                name = response.get("name", f"lan-{host}")
                caps = response.get("capabilities", [])

                configs.append(BridgeConfig(
                    name=name,
                    tier=BridgeTier.LAN,
                    host=host,
                    port=port,
                    capabilities=caps,
                    probe_timeout=timeout,
                ))
            except socket.timeout:
                break
            except (json.JSONDecodeError, ValueError):
                continue

        sock.close()
    except OSError:
        pass  # No network / broadcast not available

    return configs


def _tcp_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Quick TCP connect check — is anything listening on this port?"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except OSError:
        return False


def _parse_host_string(host_str: str, health_path: str = "/health") -> BridgeConfig:
    """Parse a host string like 'host:port' or 'http://host:port' into BridgeConfig."""
    if "://" in host_str:
        return BridgeConfig.from_url(host_str)

    parts = host_str.rsplit(":", 1)
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else 8089

    is_local = host in ("localhost", "127.0.0.1", "::1", "")
    tier = BridgeTier.LOCAL if is_local else BridgeTier.REMOTE

    return BridgeConfig(
        name=f"{'local' if is_local else 'remote'}-{port}",
        tier=tier,
        host=host or "127.0.0.1",
        port=port,
        health_path=health_path,
    )
