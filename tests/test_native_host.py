"""Tests for the Chrome Native Messaging host — CUP pipeline.

Tests the NM protocol (encode/decode), each filter in isolation,
and the full pipeline integration.  All self-contained, no network.

RED → GREEN for each test class.
"""
from __future__ import annotations

import io
import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest

import sys
# Add the native host module to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent /
                       "codeupipe" / "connect" / "extension" / "native"))
from native_host import (
    nm_read, nm_write, NativePayload,
    ReadMessageFilter, RouteActionFilter, PingFilter,
    HealthFilter, ExecFilter, ProxyFilter,
    StartFilter, StopFilter, StatusFilter,
    ConfigureFilter, ProvisionFilter, WriteMessageFilter,
    build_host_pipeline, run_pipeline,
)


# ── Helpers ──────────────────────────────────────────────────────────

def make_nm_bytes(msg: Dict[str, Any]) -> bytes:
    """Encode a message in Chrome NM protocol format."""
    encoded = json.dumps(msg).encode("utf-8")
    return struct.pack("<I", len(encoded)) + encoded


def parse_nm_bytes(raw: bytes) -> Dict[str, Any]:
    """Decode a Chrome NM protocol message."""
    msg_len = struct.unpack("<I", raw[:4])[0]
    return json.loads(raw[4:4 + msg_len].decode("utf-8"))


# ── NM Protocol Tests ────────────────────────────────────────────────

class TestNMProtocol:
    """Test Chrome Native Messaging encode/decode."""

    def test_roundtrip_simple(self):
        msg = {"action": "ping"}
        buf = io.BytesIO(make_nm_bytes(msg))
        result = nm_read(buf)
        assert result == msg

    def test_roundtrip_complex(self):
        msg = {"action": "proxy", "path": "/dream-train",
               "body": {"model_name": "Qwen/Qwen3-0.6B", "steps": 30}}
        buf = io.BytesIO(make_nm_bytes(msg))
        result = nm_read(buf)
        assert result == msg

    def test_write_then_read(self):
        msg = {"status": "ok", "device": "mps"}
        buf = io.BytesIO()
        nm_write(msg, buf)
        buf.seek(0)
        result = nm_read(buf)
        assert result == msg

    def test_read_eof(self):
        buf = io.BytesIO(b"")
        assert nm_read(buf) is None

    def test_read_short_length(self):
        buf = io.BytesIO(b"\x01\x00")
        assert nm_read(buf) is None

    def test_read_zero_length(self):
        buf = io.BytesIO(struct.pack("<I", 0))
        assert nm_read(buf) is None

    def test_read_oversized_rejected(self):
        """Messages > 1MB are rejected for safety."""
        buf = io.BytesIO(struct.pack("<I", 2 * 1024 * 1024))
        assert nm_read(buf) is None

    def test_length_encoding_little_endian(self):
        msg = {"a": 1}
        raw = make_nm_bytes(msg)
        # Verify little-endian encoding
        expected_len = len(json.dumps(msg).encode("utf-8"))
        actual_len = struct.unpack("<I", raw[:4])[0]
        assert actual_len == expected_len

    def test_multiple_messages(self):
        """Read two consecutive messages from same stream."""
        m1 = {"action": "ping"}
        m2 = {"action": "health"}
        buf = io.BytesIO(make_nm_bytes(m1) + make_nm_bytes(m2))
        assert nm_read(buf) == m1
        assert nm_read(buf) == m2
        assert nm_read(buf) is None  # EOF


# ── NativePayload Tests ─────────────────────────────────────────────

class TestNativePayload:
    """Test the lightweight Payload implementation."""

    def test_empty_payload(self):
        p = NativePayload()
        assert p.get("x") is None

    def test_get_default(self):
        p = NativePayload()
        assert p.get("x", 42) == 42

    def test_insert_returns_new(self):
        p1 = NativePayload()
        p2 = p1.insert("x", 10)
        assert p1.get("x") is None
        assert p2.get("x") == 10

    def test_immutability(self):
        p1 = NativePayload({"a": 1})
        p2 = p1.insert("b", 2)
        assert p1.get("b") is None
        assert p2.get("a") == 1
        assert p2.get("b") == 2

    def test_to_dict(self):
        p = NativePayload({"x": 1, "y": "hello"})
        assert p.to_dict() == {"x": 1, "y": "hello"}

    def test_chained_inserts(self):
        p = NativePayload().insert("a", 1).insert("b", 2).insert("c", 3)
        assert p.get("a") == 1
        assert p.get("b") == 2
        assert p.get("c") == 3


# ── ReadMessageFilter Tests ─────────────────────────────────────────

class TestReadMessageFilter:
    """Test reading NM messages into payload."""

    def test_reads_message(self):
        msg = {"action": "ping", "id": "req-001"}
        buf = io.BytesIO(make_nm_bytes(msg))
        f = ReadMessageFilter(stream=buf)
        result = f.call(NativePayload())
        assert result.get("action") == "ping"
        assert result.get("request_id") == "req-001"
        assert result.get("raw_message") == msg

    def test_eof_handling(self):
        buf = io.BytesIO(b"")
        f = ReadMessageFilter(stream=buf)
        result = f.call(NativePayload())
        assert result.get("action") == "eof"

    def test_default_action(self):
        msg = {"data": "something"}  # no 'action' key
        buf = io.BytesIO(make_nm_bytes(msg))
        f = ReadMessageFilter(stream=buf)
        result = f.call(NativePayload())
        assert result.get("action") == "unknown"


# ── RouteActionFilter Tests ─────────────────────────────────────────

class TestRouteActionFilter:
    """Test action routing."""

    def test_known_actions(self):
        f = RouteActionFilter()
        for action in ["ping", "health", "exec", "proxy", "start",
                       "stop", "provision", "status", "configure"]:
            p = NativePayload({"action": action})
            result = f.call(p)
            assert result.get("handler") == action

    def test_unknown_action(self):
        f = RouteActionFilter()
        p = NativePayload({"action": "destroy_everything"})
        result = f.call(p)
        assert result.get("handler") == "unknown"
        assert "error" in result.get("response", {})


# ── PingFilter Tests ────────────────────────────────────────────────

class TestPingFilter:
    """Test ping handler."""

    def test_pong_response(self):
        f = PingFilter()
        p = NativePayload({"handler": "ping"})
        result = f.call(p)
        resp = result.get("response")
        assert resp["status"] == "pong"
        assert resp["host"] == "cup-native-host"
        assert "python" in resp
        assert "platform" in resp

    def test_passthrough_non_ping(self):
        f = PingFilter()
        p = NativePayload({"handler": "health", "data": "keep"})
        result = f.call(p)
        assert result.get("response") is None
        assert result.get("data") == "keep"


# ── HealthFilter Tests ──────────────────────────────────────────────

class TestHealthFilter:
    """Test health check proxy."""

    def test_passthrough_non_health(self):
        f = HealthFilter()
        p = NativePayload({"handler": "proxy"})
        result = f.call(p)
        assert result.get("response") is None

    @patch("native_host.urllib.request.urlopen")
    def test_successful_health(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "status": "alive", "device": "mps",
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        f = HealthFilter(default_port=8089)
        p = NativePayload({"handler": "health", "raw_message": {}})
        result = f.call(p)
        resp = result.get("response")
        # HealthFilter merges spore_runner response, so "status" comes
        # from the mock which is "alive" (overrides the "ok" prefix)
        assert resp["status"] == "alive"
        assert resp["device"] == "mps"

    def test_failed_health_no_server(self):
        f = HealthFilter(default_port=19999)  # nothing on this port
        p = NativePayload({"handler": "health", "raw_message": {
            "port": 19999,
        }})
        result = f.call(p)
        resp = result.get("response")
        assert resp["status"] == "error"
        assert "hint" in resp


# ── ExecFilter Tests ────────────────────────────────────────────────

class TestExecFilter:
    """Test command execution with allowlist."""

    def test_allowed_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = ExecFilter(bridge_dir=tmpdir)
            p = NativePayload({
                "handler": "exec",
                "raw_message": {"command": "which python3", "cwd": tmpdir},
            })
            result = f.call(p)
            resp = result.get("response")
            assert resp["status"] == "ok"
            assert "exit_code" in resp

    def test_blocked_command(self):
        f = ExecFilter()
        p = NativePayload({
            "handler": "exec",
            "raw_message": {"command": "rm -rf /"},
        })
        result = f.call(p)
        resp = result.get("response")
        assert "error" in resp
        assert "not allowed" in resp["error"]

    def test_no_command(self):
        f = ExecFilter()
        p = NativePayload({
            "handler": "exec",
            "raw_message": {},
        })
        result = f.call(p)
        resp = result.get("response")
        assert "error" in resp

    def test_passthrough_non_exec(self):
        f = ExecFilter()
        p = NativePayload({"handler": "ping"})
        result = f.call(p)
        assert result.get("response") is None

    def test_echo_command(self):
        """echo is not in allowlist."""
        f = ExecFilter()
        p = NativePayload({
            "handler": "exec",
            "raw_message": {"command": "echo hello"},
        })
        result = f.call(p)
        resp = result.get("response")
        assert "not allowed" in resp.get("error", "")


# ── ProxyFilter Tests ───────────────────────────────────────────────

class TestProxyFilter:
    """Test HTTP proxy to spore_runner."""

    def test_passthrough_non_proxy(self):
        f = ProxyFilter()
        p = NativePayload({"handler": "ping"})
        result = f.call(p)
        assert result.get("response") is None

    @patch("native_host.urllib.request.urlopen")
    def test_successful_proxy(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "status": "complete", "job_id": "abc123",
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        f = ProxyFilter()
        p = NativePayload({
            "handler": "proxy",
            "raw_message": {
                "method": "POST",
                "path": "/dream-train",
                "body": {"model_name": "test"},
            },
        })
        result = f.call(p)
        resp = result.get("response")
        assert resp["status"] == "ok"
        assert resp["data"]["job_id"] == "abc123"


# ── StatusFilter Tests ──────────────────────────────────────────────

class TestStatusFilter:
    """Test platform status reporting."""

    def test_status_no_server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = StatusFilter(default_port=19999, bridge_dir=tmpdir)
            p = NativePayload({"handler": "status"})
            result = f.call(p)
            resp = result.get("response")
            assert resp["status"] == "ok"
            assert resp["service_alive"] is False
            assert resp["runner_installed"] is False

    def test_status_with_runner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake spore_runner.py
            (Path(tmpdir) / "spore_runner.py").write_text("# fake")
            f = StatusFilter(default_port=19999, bridge_dir=tmpdir)
            p = NativePayload({"handler": "status"})
            result = f.call(p)
            resp = result.get("response")
            assert resp["runner_installed"] is True

    def test_passthrough_non_status(self):
        f = StatusFilter()
        p = NativePayload({"handler": "ping"})
        result = f.call(p)
        assert result.get("response") is None


# ── ConfigureFilter Tests ───────────────────────────────────────────

class TestConfigureFilter:
    """Test config write/update."""

    def test_writes_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = ConfigureFilter(bridge_dir=tmpdir)
            p = NativePayload({
                "handler": "configure",
                "raw_message": {"config": {"port": 8090, "model": "test"}},
            })
            result = f.call(p)
            resp = result.get("response")
            assert resp["status"] == "ok"

            # Verify file written
            cfg = json.loads((Path(tmpdir) / "bridge.json").read_text())
            assert cfg["port"] == 8090

    def test_merges_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write initial config
            (Path(tmpdir) / "bridge.json").write_text(
                json.dumps({"port": 8089, "existing": True})
            )
            f = ConfigureFilter(bridge_dir=tmpdir)
            p = NativePayload({
                "handler": "configure",
                "raw_message": {"config": {"model": "new-model"}},
            })
            result = f.call(p)
            resp = result.get("response")
            cfg = resp["config"]
            assert cfg["port"] == 8089  # preserved
            assert cfg["existing"] is True  # preserved
            assert cfg["model"] == "new-model"  # added

    def test_no_config_error(self):
        f = ConfigureFilter()
        p = NativePayload({
            "handler": "configure",
            "raw_message": {},
        })
        result = f.call(p)
        assert "error" in result.get("response", {})


# ── ProvisionFilter Tests ───────────────────────────────────────────

class TestProvisionFilter:
    """Test the auto-provisioning engine."""

    def test_check_python_passes(self):
        f = ProvisionFilter()
        p = NativePayload({
            "handler": "provision",
            "raw_message": {
                "recipe": {
                    "id": "test",
                    "steps": [{"type": "check-python", "minVersion": "3.9"}],
                },
            },
        })
        result = f.call(p)
        resp = result.get("response")
        assert resp["success"] is True
        assert len(resp["steps_done"]) == 1

    def test_check_python_fails_high_version(self):
        f = ProvisionFilter()
        p = NativePayload({
            "handler": "provision",
            "raw_message": {
                "recipe": {
                    "id": "test",
                    "steps": [{"type": "check-python", "minVersion": "99.0"}],
                },
            },
        })
        result = f.call(p)
        resp = result.get("response")
        assert resp["success"] is False
        assert len(resp["steps_failed"]) == 1

    def test_unknown_step_skipped(self):
        f = ProvisionFilter()
        p = NativePayload({
            "handler": "provision",
            "raw_message": {
                "recipe": {
                    "id": "test",
                    "steps": [{"type": "quantum-teleport"}],
                },
            },
        })
        result = f.call(p)
        resp = result.get("response")
        assert resp["success"] is True  # unknown steps are skipped, not failed
        assert resp["steps_done"][0]["status"] == "skipped"

    def test_no_recipe_error(self):
        f = ProvisionFilter()
        p = NativePayload({
            "handler": "provision",
            "raw_message": {},
        })
        result = f.call(p)
        assert "error" in result.get("response", {})


# ── WriteMessageFilter Tests ────────────────────────────────────────

class TestWriteMessageFilter:
    """Test writing NM responses."""

    def test_writes_response(self):
        buf = io.BytesIO()
        f = WriteMessageFilter(stream=buf)
        p = NativePayload({
            "response": {"status": "pong"},
            "request_id": "req-001",
        })
        result = f.call(p)
        assert result.get("sent") is True

        # Verify what was written
        buf.seek(0)
        parsed = nm_read(buf)
        assert parsed["id"] == "req-001"
        assert parsed["status"] == "pong"

    def test_writes_error_for_no_response(self):
        buf = io.BytesIO()
        f = WriteMessageFilter(stream=buf)
        p = NativePayload({})  # no response set
        f.call(p)
        buf.seek(0)
        parsed = nm_read(buf)
        assert "error" in parsed


# ── Full Pipeline Integration Tests ─────────────────────────────────

class TestPipelineIntegration:
    """Test the complete native host pipeline end-to-end."""

    def _run_pipeline_msg(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message through the full pipeline and get the response."""
        in_buf = io.BytesIO(make_nm_bytes(msg))
        out_buf = io.BytesIO()
        filters = build_host_pipeline(
            stream_in=in_buf,
            stream_out=out_buf,
            bridge_dir=tempfile.mkdtemp(),
        )
        run_pipeline(filters, NativePayload())
        out_buf.seek(0)
        return nm_read(out_buf)

    def test_ping_e2e(self):
        resp = self._run_pipeline_msg({"action": "ping", "id": "t1"})
        assert resp["id"] == "t1"
        assert resp["status"] == "pong"
        assert resp["host"] == "cup-native-host"

    def test_status_e2e(self):
        resp = self._run_pipeline_msg({"action": "status"})
        assert "runner_installed" in resp
        assert "platform" in resp
        assert "python" in resp

    def test_unknown_action_e2e(self):
        resp = self._run_pipeline_msg({"action": "self_destruct"})
        assert "error" in resp

    def test_configure_e2e(self):
        resp = self._run_pipeline_msg({
            "action": "configure",
            "config": {"port": 9090},
        })
        assert resp["status"] == "ok"

    def test_provision_check_python_e2e(self):
        resp = self._run_pipeline_msg({
            "action": "provision",
            "recipe": {
                "id": "test-recipe",
                "steps": [
                    {"type": "check-python", "minVersion": "3.9"},
                ],
            },
        })
        assert resp["success"] is True

    def test_exec_allowed_e2e(self):
        resp = self._run_pipeline_msg({
            "action": "exec",
            "command": "which python3",
        })
        assert resp["status"] == "ok"
        assert "exit_code" in resp

    def test_exec_blocked_e2e(self):
        resp = self._run_pipeline_msg({
            "action": "exec",
            "command": "curl http://evil.com",
        })
        assert "not allowed" in resp.get("error", "")

    def test_health_no_server_e2e(self):
        resp = self._run_pipeline_msg({
            "action": "health",
            "port": 19999,
        })
        assert resp["status"] == "error"

    def test_request_id_preserved(self):
        """Request IDs flow through the entire pipeline."""
        resp = self._run_pipeline_msg({
            "action": "ping",
            "id": "correlation-abc-123",
        })
        assert resp["id"] == "correlation-abc-123"
