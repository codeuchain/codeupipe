"""Tests for codeupipe.connect bridge system.

Covers:
- BridgeConfig: construction, from_dict, from_env, from_url, serialization
- BridgeTier: ordering, ranking
- LocalBridge: probe, connect, tier selection, Filter protocol, status
- Bridge discovery: scan_localhost, scan_lan, discover_bridges
- BridgeLauncher: launch, stop, health wait
- load_bridge_configs: single & multi bridge parsing
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# ── Imports under test ───────────────────────────────────────────
from codeupipe.connect.bridge_config import (
    BridgeConfig,
    BridgeCapability,
    BridgeConfigError,
    BridgeTier,
    load_bridge_configs,
)
from codeupipe.connect.local_bridge import (
    BridgeEndpoint,
    BridgeError,
    LocalBridge,
)
from codeupipe.connect.bridge_discovery import (
    DEFAULT_PORTS,
    _parse_host_string,
    _tcp_open,
    scan_localhost,
)
from codeupipe.connect.bridge_launcher import (
    BridgeLauncher,
    LaunchResult,
)


# ── Helpers ──────────────────────────────────────────────────────

def _run_async(coro):
    """Run an async coroutine in a new event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


class _MockHealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that serves a configurable health response."""

    def do_GET(self):
        if self.path == "/health":
            data = getattr(self.server, "health_data", {
                "status": "alive",
                "device": "cpu",
                "torch_version": "2.0.0",
                "cuda": False,
                "mps": True,
                "swarm": True,
                "queue": True,
            })
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body) if body else {}

        response = {"status": "ok", "echo": data}
        resp_body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def log_message(self, format, *args):
        pass  # Suppress output


@pytest.fixture()
def mock_server():
    """Start a mock HTTP server and return (server, port)."""
    server = HTTPServer(("127.0.0.1", 0), _MockHealthHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, port
    server.shutdown()


@pytest.fixture()
def mock_server_custom():
    """Factory fixture — start a mock server with custom health data."""
    servers = []

    def _create(health_data=None):
        server = HTTPServer(("127.0.0.1", 0), _MockHealthHandler)
        if health_data:
            server.health_data = health_data
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        return server, port

    yield _create

    for s in servers:
        s.shutdown()


# ╔═══════════════════════════════════════════════════════════════╗
# ║  BridgeConfig Tests                                          ║
# ╚═══════════════════════════════════════════════════════════════╝

class TestBridgeConfig:
    """BridgeConfig construction and serialization."""

    def test_defaults(self):
        cfg = BridgeConfig()
        assert cfg.name == "default"
        assert cfg.tier == BridgeTier.LOCAL
        assert cfg.host == "localhost"
        assert cfg.port == 8089
        assert cfg.health_path == "/health"
        assert cfg.secret == ""
        assert cfg.capabilities == []
        assert cfg.probe_timeout == 3.0
        assert cfg.auto_start == ""

    def test_base_url_localhost(self):
        cfg = BridgeConfig(host="localhost", port=8089)
        assert cfg.base_url == "http://localhost:8089"

    def test_base_url_remote(self):
        cfg = BridgeConfig(host="gpu.example.com", port=443)
        assert cfg.base_url == "https://gpu.example.com:443"

    def test_base_url_ip(self):
        cfg = BridgeConfig(host="127.0.0.1", port=9090)
        assert cfg.base_url == "http://127.0.0.1:9090"

    def test_health_url(self):
        cfg = BridgeConfig(port=8089, health_path="/health")
        assert cfg.health_url == "http://localhost:8089/health"

    def test_health_url_custom_path(self):
        cfg = BridgeConfig(port=5000, health_path="/api/status")
        assert cfg.health_url == "http://localhost:5000/api/status"

    def test_from_dict(self):
        data = {
            "tier": "remote",
            "host": "gpu.example.com",
            "port": 443,
            "secret": "mysecret",
            "capabilities": ["torch", "cuda"],
        }
        cfg = BridgeConfig.from_dict(data, name="my-gpu")
        assert cfg.name == "my-gpu"
        assert cfg.tier == "remote"
        assert cfg.host == "gpu.example.com"
        assert cfg.port == 443
        assert cfg.secret == "mysecret"
        assert cfg.capabilities == ["torch", "cuda"]

    def test_from_dict_defaults(self):
        cfg = BridgeConfig.from_dict({})
        assert cfg.host == "localhost"
        assert cfg.port == 8089
        assert cfg.tier == BridgeTier.LOCAL

    def test_from_env(self):
        env = {
            "BRIDGE_HOST": "192.168.1.42",
            "BRIDGE_PORT": "9090",
            "BRIDGE_SECRET": "s3cret",
            "BRIDGE_TIER": "lan",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = BridgeConfig.from_env("BRIDGE")
        assert cfg.host == "192.168.1.42"
        assert cfg.port == 9090
        assert cfg.secret == "s3cret"
        assert cfg.tier == "lan"

    def test_from_env_defaults(self):
        """from_env with no env vars set uses defaults."""
        # Clear any existing BRIDGE_ vars
        with patch.dict(os.environ, {}, clear=True):
            cfg = BridgeConfig.from_env("BRIDGE")
        assert cfg.host == "localhost"
        assert cfg.port == 8089

    def test_from_url_localhost(self):
        cfg = BridgeConfig.from_url("http://localhost:8089")
        assert cfg.host == "localhost"
        assert cfg.port == 8089
        assert cfg.tier == BridgeTier.LOCAL

    def test_from_url_remote(self):
        cfg = BridgeConfig.from_url("https://gpu.example.com:443")
        assert cfg.host == "gpu.example.com"
        assert cfg.port == 443
        assert cfg.tier == BridgeTier.REMOTE

    def test_from_url_ip(self):
        cfg = BridgeConfig.from_url("http://127.0.0.1:5000")
        assert cfg.tier == BridgeTier.LOCAL

    def test_to_dict_roundtrip(self):
        cfg = BridgeConfig(
            name="test", tier="lan", host="192.168.1.1", port=9090,
            secret="abc", capabilities=["torch"],
        )
        d = cfg.to_dict()
        cfg2 = BridgeConfig.from_dict(d)
        assert cfg2.name == cfg.name
        assert cfg2.tier == cfg.tier
        assert cfg2.host == cfg.host
        assert cfg2.port == cfg.port
        assert cfg2.secret == cfg.secret
        assert cfg2.capabilities == cfg.capabilities

    def test_with_overrides(self):
        cfg = BridgeConfig(name="original", port=8089)
        cfg2 = cfg.with_overrides(port=9090, secret="new")
        assert cfg.port == 8089  # original unchanged
        assert cfg2.port == 9090
        assert cfg2.secret == "new"
        assert cfg2.name == "original"  # inherited


# ╔═══════════════════════════════════════════════════════════════╗
# ║  BridgeTier Tests                                            ║
# ╚═══════════════════════════════════════════════════════════════╝

class TestBridgeTier:
    """Tier ordering and ranking."""

    def test_order(self):
        assert BridgeTier.ORDER == ["local", "lan", "remote", "wasm"]

    def test_rank_local(self):
        assert BridgeTier.rank("local") == 0

    def test_rank_lan(self):
        assert BridgeTier.rank("lan") == 1

    def test_rank_remote(self):
        assert BridgeTier.rank("remote") == 2

    def test_rank_wasm(self):
        assert BridgeTier.rank("wasm") == 3

    def test_rank_unknown(self):
        assert BridgeTier.rank("unknown") == 4  # beyond known tiers

    def test_local_preferred_over_remote(self):
        assert BridgeTier.rank("local") < BridgeTier.rank("remote")

    def test_lan_preferred_over_wasm(self):
        assert BridgeTier.rank("lan") < BridgeTier.rank("wasm")


# ╔═══════════════════════════════════════════════════════════════╗
# ║  BridgeCapability Tests                                      ║
# ╚═══════════════════════════════════════════════════════════════╝

class TestBridgeCapability:
    """Well-known capability constants."""

    def test_torch(self):
        assert BridgeCapability.TORCH == "torch"

    def test_cuda(self):
        assert BridgeCapability.CUDA == "cuda"

    def test_mps(self):
        assert BridgeCapability.MPS == "mps"

    def test_swarm(self):
        assert BridgeCapability.SWARM == "swarm"

    def test_queue(self):
        assert BridgeCapability.QUEUE == "queue"


# ╔═══════════════════════════════════════════════════════════════╗
# ║  load_bridge_configs Tests                                   ║
# ╚═══════════════════════════════════════════════════════════════╝

class TestLoadBridgeConfigs:
    """Parse bridge configs from dict (cup.toml style)."""

    def test_single_bridge(self):
        raw = {"host": "localhost", "port": 8089, "tier": "local"}
        configs = load_bridge_configs(raw)
        assert len(configs) == 1
        assert configs[0].host == "localhost"
        assert configs[0].port == 8089

    def test_multiple_bridges(self):
        raw = {
            "gpu": {"host": "gpu.local", "port": 8089, "tier": "lan"},
            "cloud": {"host": "gpu.cloud.com", "port": 443, "tier": "remote"},
        }
        configs = load_bridge_configs(raw)
        assert len(configs) == 2
        # Should be sorted by tier: lan before remote
        assert configs[0].tier == "lan"
        assert configs[1].tier == "remote"

    def test_sorted_by_tier(self):
        raw = {
            "cloud": {"host": "cloud.com", "port": 443, "tier": "remote"},
            "local": {"host": "localhost", "port": 8089, "tier": "local"},
            "lan": {"host": "192.168.1.1", "port": 8089, "tier": "lan"},
        }
        configs = load_bridge_configs(raw)
        tiers = [c.tier for c in configs]
        assert tiers == ["local", "lan", "remote"]

    def test_empty_dict(self):
        configs = load_bridge_configs({})
        assert len(configs) == 0


# ╔═══════════════════════════════════════════════════════════════╗
# ║  BridgeEndpoint Tests                                        ║
# ╚═══════════════════════════════════════════════════════════════╝

class TestBridgeEndpoint:
    """Runtime endpoint state."""

    def test_defaults(self):
        ep = BridgeEndpoint(config=BridgeConfig())
        assert not ep.alive
        assert ep.tier == BridgeTier.LOCAL
        assert ep.capabilities == []

    def test_has_capability(self):
        ep = BridgeEndpoint(
            config=BridgeConfig(),
            capabilities=["torch", "mps", "swarm"],
        )
        assert ep.has_capability("torch")
        assert ep.has_capability("mps")
        assert not ep.has_capability("cuda")

    def test_has_all(self):
        ep = BridgeEndpoint(
            config=BridgeConfig(),
            capabilities=["torch", "mps", "swarm"],
        )
        assert ep.has_all(["torch", "mps"])
        assert not ep.has_all(["torch", "cuda"])

    def test_to_dict(self):
        ep = BridgeEndpoint(
            config=BridgeConfig(name="test"),
            alive=True,
            device="mps",
            latency_ms=12.5,
        )
        d = ep.to_dict()
        assert d["name"] == "test"
        assert d["alive"] is True
        assert d["device"] == "mps"
        assert d["latency_ms"] == 12.5


# ╔═══════════════════════════════════════════════════════════════╗
# ║  LocalBridge Tests — Mock Server                             ║
# ╚═══════════════════════════════════════════════════════════════╝

class TestLocalBridgeProbe:
    """Probe and connect with a real mock HTTP server."""

    def test_probe_alive(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        endpoints = bridge.probe_sync()

        assert len(endpoints) == 1
        assert endpoints[0].alive
        assert bridge.is_alive
        assert bridge.tier == BridgeTier.LOCAL

    def test_probe_dead_port(self):
        """Probing a closed port marks endpoint as dead."""
        cfg = BridgeConfig(host="127.0.0.1", port=19999, probe_timeout=0.5)
        bridge = LocalBridge(cfg)
        endpoints = bridge.probe_sync()

        assert len(endpoints) == 1
        assert not endpoints[0].alive
        assert not bridge.is_alive
        assert bridge.tier == BridgeTier.WASM

    def test_probe_extracts_capabilities(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        bridge.probe_sync()

        caps = bridge.capabilities
        assert "torch" in caps
        assert "mps" in caps
        assert "swarm" in caps
        assert "queue" in caps

    def test_probe_extracts_device(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        bridge.probe_sync()
        assert bridge.device == "cpu"

    def test_connect_async(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        result = _run_async(bridge.connect())
        assert result is True
        assert bridge.is_alive

    def test_probe_latency(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        bridge.probe_sync()

        ep = bridge.active_endpoint
        assert ep is not None
        assert ep.latency_ms > 0
        assert ep.latency_ms < 5000  # Should be fast on localhost


class TestLocalBridgeMultiEndpoint:
    """Tier selection with multiple endpoints."""

    def test_prefers_local_over_remote(self, mock_server_custom):
        _, port1 = mock_server_custom({"status": "alive", "device": "mps"})
        _, port2 = mock_server_custom({"status": "alive", "device": "cuda"})

        configs = [
            BridgeConfig(name="remote", tier=BridgeTier.REMOTE, host="127.0.0.1", port=port2),
            BridgeConfig(name="local", tier=BridgeTier.LOCAL, host="127.0.0.1", port=port1),
        ]
        bridge = LocalBridge(configs)
        bridge.probe_sync()

        assert bridge.is_alive
        assert bridge.tier == BridgeTier.LOCAL
        assert bridge.active_endpoint.config.name == "local"

    def test_falls_back_to_remote(self, mock_server_custom):
        _, port = mock_server_custom({"status": "alive", "device": "cuda"})

        configs = [
            BridgeConfig(name="local-dead", tier=BridgeTier.LOCAL, host="127.0.0.1", port=19999, probe_timeout=0.3),
            BridgeConfig(name="remote-alive", tier=BridgeTier.REMOTE, host="127.0.0.1", port=port),
        ]
        bridge = LocalBridge(configs)
        bridge.probe_sync()

        assert bridge.is_alive
        assert bridge.tier == BridgeTier.REMOTE
        assert bridge.active_endpoint.config.name == "remote-alive"

    def test_all_dead_returns_wasm(self):
        configs = [
            BridgeConfig(name="dead1", host="127.0.0.1", port=19998, probe_timeout=0.3),
            BridgeConfig(name="dead2", host="127.0.0.1", port=19999, probe_timeout=0.3),
        ]
        bridge = LocalBridge(configs)
        bridge.probe_sync()

        assert not bridge.is_alive
        assert bridge.tier == BridgeTier.WASM
        assert bridge.device == "wasm"

    def test_capability_filter(self, mock_server_custom):
        _, port1 = mock_server_custom({"status": "alive", "device": "cpu"})
        _, port2 = mock_server_custom({"status": "alive", "device": "cuda", "cuda": True, "torch_version": "2.0"})

        configs = [
            BridgeConfig(name="no-cuda", tier=BridgeTier.LOCAL, host="127.0.0.1", port=port1),
            BridgeConfig(name="has-cuda", tier=BridgeTier.LAN, host="127.0.0.1", port=port2),
        ]
        bridge = LocalBridge(configs, required_capabilities=["cuda"])
        bridge.probe_sync()

        assert bridge.is_alive
        assert bridge.active_endpoint.config.name == "has-cuda"


class TestLocalBridgeRequest:
    """Making requests through the bridge."""

    def test_request_sync(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        bridge.probe_sync()

        result = bridge.request_sync("/health")
        assert result["status"] == "alive"

    def test_request_post(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        bridge.probe_sync()

        result = bridge.request_sync(
            "/anything", method="POST", body={"key": "value"},
        )
        assert result["echo"]["key"] == "value"

    def test_request_async(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        bridge.probe_sync()

        result = _run_async(bridge.request("/health"))
        assert result["status"] == "alive"

    def test_delegate_async(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        bridge.probe_sync()

        result = _run_async(bridge.delegate("/train", body={"steps": 10}))
        assert result["echo"]["steps"] == 10

    def test_request_no_active_raises(self):
        bridge = LocalBridge(BridgeConfig(port=19999, probe_timeout=0.3))
        bridge.probe_sync()
        with pytest.raises(BridgeError, match="No active"):
            bridge.request_sync("/health")


class TestLocalBridgeFilterProtocol:
    """LocalBridge as a CUP Filter (async call)."""

    def test_call_with_live_endpoint(self, mock_server):
        """Filter call delegates to bridge and sets tier/device."""
        from codeupipe import Payload
        _, port = mock_server

        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg, delegate_path="/health")

        payload = Payload().insert("some_data", 42)
        result = _run_async(bridge.call(payload))

        assert result.get("bridge_alive") is True
        assert result.get("bridge_tier") == BridgeTier.LOCAL
        assert result.get("bridge_device") == "cpu"
        assert result.get("bridge_response") is not None

    def test_call_with_dead_endpoint(self):
        """Filter call with no live endpoint returns wasm tier."""
        from codeupipe import Payload

        cfg = BridgeConfig(port=19999, probe_timeout=0.3)
        bridge = LocalBridge(cfg)

        payload = Payload().insert("data", "test")
        result = _run_async(bridge.call(payload))

        assert result.get("bridge_alive") is False
        assert result.get("bridge_tier") == BridgeTier.WASM
        assert result.get("bridge_device") == "wasm"

    def test_call_auto_probes(self, mock_server):
        """Auto-probe on first call when auto_probe=True."""
        from codeupipe import Payload
        _, port = mock_server

        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg, auto_probe=True, delegate_path="/health")

        payload = Payload()
        result = _run_async(bridge.call(payload))
        assert result.get("bridge_alive") is True

    def test_call_custom_path(self, mock_server):
        """bridge_path in payload overrides default delegate_path."""
        from codeupipe import Payload
        _, port = mock_server

        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg, delegate_path="/wrong")
        bridge.probe_sync()

        payload = Payload().insert("bridge_path", "/health")
        result = _run_async(bridge.call(payload))
        assert result.get("bridge_alive") is True


class TestLocalBridgeStatus:
    """Status introspection."""

    def test_status_alive(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        bridge.probe_sync()

        status = bridge.status()
        assert status["is_alive"] is True
        assert status["tier"] == BridgeTier.LOCAL
        assert status["probed"] is True
        assert len(status["endpoints"]) == 1

    def test_status_disconnected(self):
        bridge = LocalBridge(BridgeConfig(port=19999, probe_timeout=0.3))
        bridge.probe_sync()

        status = bridge.status()
        assert status["is_alive"] is False
        assert status["tier"] == BridgeTier.WASM

    def test_repr(self, mock_server):
        _, port = mock_server
        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg)
        bridge.probe_sync()

        r = repr(bridge)
        assert "alive" in r
        assert "local" in r


# ╔═══════════════════════════════════════════════════════════════╗
# ║  Discovery Tests                                             ║
# ╚═══════════════════════════════════════════════════════════════╝

class TestDiscovery:
    """Bridge discovery utilities."""

    def test_default_ports(self):
        assert 8089 in DEFAULT_PORTS
        assert isinstance(DEFAULT_PORTS, list)

    def test_tcp_open_closed_port(self):
        assert _tcp_open("127.0.0.1", 19999, timeout=0.3) is False

    def test_tcp_open_live_port(self, mock_server):
        _, port = mock_server
        assert _tcp_open("127.0.0.1", port, timeout=1.0) is True

    def test_scan_localhost_finds_live(self, mock_server):
        _, port = mock_server
        configs = scan_localhost(ports=[port], timeout=1.0)
        assert len(configs) == 1
        assert configs[0].port == port
        assert configs[0].tier == BridgeTier.LOCAL

    def test_scan_localhost_skips_dead(self):
        configs = scan_localhost(ports=[19999], timeout=0.3)
        assert len(configs) == 0

    def test_parse_host_string_simple(self):
        cfg = _parse_host_string("192.168.1.42:8089")
        assert cfg.host == "192.168.1.42"
        assert cfg.port == 8089
        assert cfg.tier == BridgeTier.REMOTE

    def test_parse_host_string_localhost(self):
        cfg = _parse_host_string("localhost:9090")
        assert cfg.host == "localhost"
        assert cfg.port == 9090
        assert cfg.tier == BridgeTier.LOCAL

    def test_parse_host_string_url(self):
        cfg = _parse_host_string("http://gpu.example.com:443")
        assert cfg.host == "gpu.example.com"
        assert cfg.port == 443
        assert cfg.tier == BridgeTier.REMOTE

    def test_parse_host_string_default_port(self):
        cfg = _parse_host_string("localhost")
        assert cfg.port == 8089


# ╔═══════════════════════════════════════════════════════════════╗
# ║  Launcher Tests                                              ║
# ╚═══════════════════════════════════════════════════════════════╝

class TestLauncher:
    """BridgeLauncher process management."""

    def test_no_command_returns_failure(self):
        cfg = BridgeConfig(auto_start="")
        launcher = BridgeLauncher(cfg)
        result = launcher.launch()
        assert not result.success
        assert "No auto_start" in result.message

    def test_launch_result_to_dict(self):
        result = LaunchResult(success=True, pid=1234, message="Started")
        d = result.to_dict()
        assert d["success"] is True
        assert d["pid"] == 1234
        assert d["message"] == "Started"

    def test_is_running_no_process(self):
        cfg = BridgeConfig()
        launcher = BridgeLauncher(cfg)
        assert not launcher.is_running
        assert launcher.pid == 0

    def test_stop_no_process(self):
        cfg = BridgeConfig()
        launcher = BridgeLauncher(cfg)
        assert launcher.stop() is False

    def test_launch_with_mock_command(self, mock_server):
        """Launch a real process (sleep) and verify it starts."""
        import sys
        _, port = mock_server

        cfg = BridgeConfig(
            host="127.0.0.1",
            port=port,
            auto_start=f"{sys.executable} -c",
            auto_start_args=["import time; time.sleep(60)"],
        )
        launcher = BridgeLauncher(cfg, wait_timeout=3, poll_interval=0.5)

        # The health endpoint is already running via mock_server,
        # so the launcher should detect it and succeed
        result = launcher.launch()
        assert result.success
        assert launcher.is_running
        assert launcher.pid > 0

        # Cleanup
        launcher.stop()
        assert not launcher.is_running


# ╔═══════════════════════════════════════════════════════════════╗
# ║  Integration Tests                                           ║
# ╚═══════════════════════════════════════════════════════════════╝

class TestBridgeIntegration:
    """End-to-end integration tests."""

    def test_full_lifecycle(self, mock_server):
        """probe → connect → delegate → status."""
        _, port = mock_server

        # Configure
        cfg = BridgeConfig(host="127.0.0.1", port=port)

        # Probe
        bridge = LocalBridge(cfg)
        result = _run_async(bridge.connect())
        assert result is True
        assert bridge.is_alive

        # Delegate work
        response = _run_async(bridge.delegate(
            "/train", body={"model": "test", "steps": 5},
        ))
        assert response["status"] == "ok"
        assert response["echo"]["model"] == "test"

        # Check status
        status = bridge.status()
        assert status["is_alive"] is True
        assert status["tier"] == "local"

    def test_multi_tier_fallback(self, mock_server_custom):
        """Dead local → alive remote = remote tier selected."""
        _, remote_port = mock_server_custom({
            "status": "alive", "device": "cuda",
            "cuda": True, "torch_version": "2.0",
        })

        configs = [
            BridgeConfig(name="dead-local", tier="local", host="127.0.0.1",
                         port=19999, probe_timeout=0.3),
            BridgeConfig(name="alive-remote", tier="remote", host="127.0.0.1",
                         port=remote_port),
        ]

        bridge = LocalBridge(configs)
        _run_async(bridge.connect())

        assert bridge.is_alive
        assert bridge.tier == "remote"
        assert bridge.device == "cuda"
        assert "cuda" in bridge.capabilities

    def test_bridge_in_pipeline(self, mock_server):
        """LocalBridge used as a Filter in a CUP Pipeline."""
        from codeupipe import Payload, Pipeline
        _, port = mock_server

        cfg = BridgeConfig(host="127.0.0.1", port=port)
        bridge = LocalBridge(cfg, delegate_path="/health")

        pipeline = Pipeline()
        pipeline.add_filter(bridge, name="bridge")

        payload = Payload()
        result = _run_async(pipeline.run(payload))

        assert result.get("bridge_alive") is True
        assert result.get("bridge_tier") == "local"

    def test_config_from_url_to_bridge(self, mock_server):
        """Full path: URL string → config → bridge → alive."""
        _, port = mock_server

        cfg = BridgeConfig.from_url(f"http://127.0.0.1:{port}")
        bridge = LocalBridge(cfg)
        bridge.probe_sync()

        assert bridge.is_alive
        assert bridge.tier == "local"
