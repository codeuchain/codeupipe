#!/usr/bin/env python3
"""Native Messaging Host — Chrome ↔ Desktop bridge via CUP pipeline.

Chrome launches this process on demand when the extension sends a
native message.  Communication uses Chrome's Native Messaging protocol:
  - Messages are length-prefixed (4 bytes, little-endian) JSON.
  - stdin for incoming, stdout for outgoing.

This host is itself a CUP pipeline:
  ReadMessage → RouteAction → [HealthFilter | ExecFilter | ProxyFilter | StartFilter] → WriteMessage

Zero external deps beyond codeupipe.  stdlib only for I/O,
urllib for proxying to spore_runner.

Usage:
    # Chrome launches this automatically via the NM host manifest.
    # For manual testing:
    echo -ne '\\x0d\\x00\\x00\\x00{"action":"ping"}' | python3 native_host.py
"""
from __future__ import annotations

import json
import os
import platform
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Chrome Native Messaging Protocol ─────────────────────────────────

def nm_read(stream=None) -> Optional[Dict[str, Any]]:
    """Read one Native Messaging message from stdin.

    Chrome NM protocol: 4-byte little-endian length prefix, then JSON.
    Returns None on EOF.
    """
    inp = stream or sys.stdin.buffer
    raw_len = inp.read(4)
    if len(raw_len) < 4:
        return None
    msg_len = struct.unpack("<I", raw_len)[0]
    if msg_len == 0:
        return None
    if msg_len > 1024 * 1024:  # 1MB safety limit
        return None
    raw_msg = inp.read(msg_len)
    if len(raw_msg) < msg_len:
        return None
    return json.loads(raw_msg.decode("utf-8"))


def nm_write(msg: Dict[str, Any], stream=None) -> None:
    """Write one Native Messaging message to stdout.

    Chrome NM protocol: 4-byte little-endian length prefix, then JSON.
    """
    out = stream or sys.stdout.buffer
    encoded = json.dumps(msg, default=str).encode("utf-8")
    out.write(struct.pack("<I", len(encoded)))
    out.write(encoded)
    out.flush()


# ── CUP-style Payload (lightweight, self-contained) ─────────────────
#
# We keep this self-contained so the native host has zero import deps
# beyond stdlib.  It mirrors codeupipe.Payload's immutable API.

class NativePayload:
    """Immutable payload for native host pipeline."""

    __slots__ = ("_data",)

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self._data: Dict[str, Any] = dict(data) if data else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def insert(self, key: str, value: Any) -> "NativePayload":
        new_data = dict(self._data)
        new_data[key] = value
        return NativePayload(new_data)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


# ── Filters (each does one thing) ────────────────────────────────────

class ReadMessageFilter:
    """Read a Chrome NM message from stdin into the payload."""

    def __init__(self, stream=None):
        self._stream = stream

    def call(self, payload: NativePayload) -> NativePayload:
        msg = nm_read(self._stream)
        if msg is None:
            return payload.insert("action", "eof").insert("raw_message", None)
        return (
            payload
            .insert("raw_message", msg)
            .insert("action", msg.get("action", "unknown"))
            .insert("request_id", msg.get("id", ""))
        )


class RouteActionFilter:
    """Route based on action field — sets 'handler' key."""

    KNOWN_ACTIONS = frozenset([
        "ping", "health", "exec", "proxy", "start", "stop",
        "provision", "status", "configure",
    ])

    def call(self, payload: NativePayload) -> NativePayload:
        action = payload.get("action", "unknown")
        if action in self.KNOWN_ACTIONS:
            return payload.insert("handler", action)
        return payload.insert("handler", "unknown").insert(
            "response", {"error": f"Unknown action: {action}"}
        )


class PingFilter:
    """Handle ping — immediate response, no side effects."""

    def call(self, payload: NativePayload) -> NativePayload:
        if payload.get("handler") != "ping":
            return payload
        return payload.insert("response", {
            "status": "pong",
            "version": "1.0.0",
            "platform": platform.system(),
            "python": platform.python_version(),
            "host": "cup-native-host",
        })


class HealthFilter:
    """Proxy health check to spore_runner."""

    def __init__(self, default_port: int = 8089):
        self._default_port = default_port

    def call(self, payload: NativePayload) -> NativePayload:
        if payload.get("handler") != "health":
            return payload
        msg = payload.get("raw_message", {}) or {}
        port = msg.get("port", self._default_port)
        url = msg.get("url", f"http://localhost:{port}/health")

        try:
            req = urllib.request.Request(url, method="GET",
                                         headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return payload.insert("response", {
                "status": "ok",
                **data,
            })
        except Exception as e:
            return payload.insert("response", {
                "status": "error",
                "error": str(e),
                "hint": "Is spore_runner running?",
            })


class ExecFilter:
    """Execute a shell command and return output.

    Security: Only allows commands in the allowlist.
    """

    ALLOWLIST = frozenset([
        "pip", "pip3", "python3", "python",
        "which", "uname", "cat", "ls",
    ])

    def __init__(self, bridge_dir: Optional[str] = None):
        self._bridge_dir = bridge_dir or str(
            Path.home() / ".cup-bridge"
        )

    def call(self, payload: NativePayload) -> NativePayload:
        if payload.get("handler") != "exec":
            return payload
        msg = payload.get("raw_message", {}) or {}
        command = msg.get("command", "")
        if not command:
            return payload.insert("response", {"error": "No command specified"})

        # Security: check allowlist
        parts = command.split()
        base_cmd = Path(parts[0]).name if parts else ""
        if base_cmd not in self.ALLOWLIST:
            return payload.insert("response", {
                "error": f"Command not allowed: {base_cmd}",
                "allowed": sorted(self.ALLOWLIST),
            })

        cwd = msg.get("cwd", self._bridge_dir)
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=120, cwd=cwd,
            )
            return payload.insert("response", {
                "status": "ok",
                "exit_code": result.returncode,
                "stdout": result.stdout[-4096:],  # cap output
                "stderr": result.stderr[-2048:],
            })
        except subprocess.TimeoutExpired:
            return payload.insert("response", {
                "status": "error", "error": "Command timed out (120s)",
            })
        except Exception as e:
            return payload.insert("response", {
                "status": "error", "error": str(e),
            })


class ProxyFilter:
    """Proxy an HTTP request to spore_runner."""

    def __init__(self, default_port: int = 8089):
        self._default_port = default_port

    def call(self, payload: NativePayload) -> NativePayload:
        if payload.get("handler") != "proxy":
            return payload
        msg = payload.get("raw_message", {}) or {}
        method = msg.get("method", "GET").upper()
        port = msg.get("port", self._default_port)
        path = msg.get("path", "/health")
        url = msg.get("url", f"http://localhost:{port}{path}")
        body = msg.get("body")
        secret = msg.get("secret", "")

        headers = {"Accept": "application/json"}
        if secret:
            headers["X-Spore-Secret"] = secret

        data_bytes = None
        if body is not None:
            data_bytes = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        try:
            req = urllib.request.Request(
                url, data=data_bytes, headers=headers, method=method,
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                resp_body = json.loads(resp.read().decode("utf-8"))
            return payload.insert("response", {
                "status": "ok",
                "data": resp_body,
            })
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
            except Exception:
                err_body = {"error": str(e)}
            return payload.insert("response", {
                "status": "error",
                "code": e.code,
                "data": err_body,
            })
        except Exception as e:
            return payload.insert("response", {
                "status": "error", "error": str(e),
            })


class StartFilter:
    """Start spore_runner as a background process."""

    def __init__(self, bridge_dir: Optional[str] = None):
        self._bridge_dir = bridge_dir or str(
            Path.home() / ".cup-bridge"
        )

    def call(self, payload: NativePayload) -> NativePayload:
        if payload.get("handler") != "start":
            return payload
        msg = payload.get("raw_message", {}) or {}
        port = msg.get("port", 8089)
        extra_args = msg.get("args", [])

        runner = Path(self._bridge_dir) / "spore_runner.py"
        if not runner.exists():
            return payload.insert("response", {
                "status": "error",
                "error": f"spore_runner.py not found at {runner}",
                "hint": "Run provision first",
            })

        cmd = [
            sys.executable, str(runner),
            "--port", str(port),
            "--queue-local",
        ] + extra_args

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            # Wait briefly for crash
            time.sleep(1)
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode("utf-8", errors="replace")[-1024:]
                return payload.insert("response", {
                    "status": "error",
                    "error": f"Process exited immediately: {stderr}",
                })
            return payload.insert("response", {
                "status": "ok",
                "pid": proc.pid,
                "port": port,
                "message": f"spore_runner started on port {port}",
            })
        except Exception as e:
            return payload.insert("response", {
                "status": "error", "error": str(e),
            })


class StopFilter:
    """Stop a running spore_runner by PID."""

    def call(self, payload: NativePayload) -> NativePayload:
        if payload.get("handler") != "stop":
            return payload
        msg = payload.get("raw_message", {}) or {}
        pid = msg.get("pid")
        if not pid:
            return payload.insert("response", {"error": "No PID specified"})
        try:
            os.kill(int(pid), 15)  # SIGTERM
            return payload.insert("response", {
                "status": "ok", "message": f"Sent SIGTERM to {pid}",
            })
        except ProcessLookupError:
            return payload.insert("response", {
                "status": "ok", "message": f"Process {pid} already gone",
            })
        except Exception as e:
            return payload.insert("response", {
                "status": "error", "error": str(e),
            })


class StatusFilter:
    """Return overall platform status."""

    def __init__(self, default_port: int = 8089, bridge_dir: Optional[str] = None):
        self._default_port = default_port
        self._bridge_dir = bridge_dir or str(Path.home() / ".cup-bridge")

    def call(self, payload: NativePayload) -> NativePayload:
        if payload.get("handler") != "status":
            return payload

        bridge_path = Path(self._bridge_dir)
        has_runner = (bridge_path / "spore_runner.py").exists()
        has_config = (bridge_path / "bridge.json").exists()

        # Check if spore_runner is responding
        alive = False
        device = "unknown"
        try:
            url = f"http://localhost:{self._default_port}/health"
            req = urllib.request.Request(url, method="GET",
                                         headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                alive = data.get("status") == "alive"
                device = data.get("device", "unknown")
        except Exception:
            pass

        return payload.insert("response", {
            "status": "ok",
            "bridge_dir": self._bridge_dir,
            "runner_installed": has_runner,
            "config_exists": has_config,
            "service_alive": alive,
            "device": device,
            "port": self._default_port,
            "platform": platform.system(),
            "python": platform.python_version(),
        })


class ConfigureFilter:
    """Write or update bridge configuration."""

    def __init__(self, bridge_dir: Optional[str] = None):
        self._bridge_dir = bridge_dir or str(Path.home() / ".cup-bridge")

    def call(self, payload: NativePayload) -> NativePayload:
        if payload.get("handler") != "configure":
            return payload
        msg = payload.get("raw_message", {}) or {}
        config = msg.get("config", {})
        if not config:
            return payload.insert("response", {"error": "No config provided"})

        bridge_path = Path(self._bridge_dir)
        bridge_path.mkdir(parents=True, exist_ok=True)
        config_file = bridge_path / "bridge.json"

        # Merge with existing config
        existing = {}
        if config_file.exists():
            try:
                existing = json.loads(config_file.read_text())
            except Exception:
                pass
        existing.update(config)

        config_file.write_text(json.dumps(existing, indent=2))
        return payload.insert("response", {
            "status": "ok",
            "config_path": str(config_file),
            "config": existing,
        })


class ProvisionFilter:
    """Download and install scripts from the platform site.

    This is the auto-installer: given a recipe, downloads scripts
    from GitHub Pages, installs Python deps, and sets up the service.
    """

    def __init__(self, bridge_dir: Optional[str] = None,
                 base_url: str = ""):
        self._bridge_dir = bridge_dir or str(Path.home() / ".cup-bridge")
        self._base_url = base_url or "https://codeuchain.github.io/cup-platform"

    def call(self, payload: NativePayload) -> NativePayload:
        if payload.get("handler") != "provision":
            return payload
        msg = payload.get("raw_message", {}) or {}
        recipe = msg.get("recipe", {})
        if not recipe:
            return payload.insert("response", {"error": "No recipe provided"})

        bridge_path = Path(self._bridge_dir)
        bridge_path.mkdir(parents=True, exist_ok=True)

        steps_done = []
        steps_failed = []

        for step in recipe.get("steps", []):
            step_type = step.get("type", "")
            try:
                if step_type == "check-python":
                    min_ver = step.get("minVersion", "3.9")
                    major, minor = min_ver.split(".")
                    if sys.version_info < (int(major), int(minor)):
                        steps_failed.append({
                            "type": step_type,
                            "error": f"Python {min_ver}+ required, "
                                     f"have {platform.python_version()}",
                        })
                        continue
                    steps_done.append({"type": step_type, "status": "ok"})

                elif step_type == "pip-install":
                    packages = step.get("packages", [])
                    if packages:
                        cmd = [sys.executable, "-m", "pip", "install",
                               "--quiet"] + packages
                        result = subprocess.run(
                            cmd, capture_output=True, text=True, timeout=300,
                        )
                        if result.returncode != 0:
                            steps_failed.append({
                                "type": step_type,
                                "error": result.stderr[-512:],
                            })
                            continue
                    steps_done.append({"type": step_type, "status": "ok",
                                       "packages": packages})

                elif step_type == "download":
                    url = step.get("url", "")
                    dest = step.get("dest", "").replace(
                        "~", str(Path.home()))
                    if url and dest:
                        dest_path = Path(dest)
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        req = urllib.request.Request(url)
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            dest_path.write_bytes(resp.read())
                        dest_path.chmod(0o755)
                        steps_done.append({
                            "type": step_type, "status": "ok",
                            "dest": str(dest_path),
                        })

                elif step_type == "start-service":
                    command = step.get("command", "").replace(
                        "~", str(Path.home()))
                    if command:
                        proc = subprocess.Popen(
                            command, shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            start_new_session=True,
                        )
                        time.sleep(2)
                        if proc.poll() is not None:
                            steps_failed.append({
                                "type": step_type,
                                "error": "Process exited immediately",
                            })
                            continue
                        steps_done.append({
                            "type": step_type, "status": "ok",
                            "pid": proc.pid,
                        })

                else:
                    steps_done.append({
                        "type": step_type, "status": "skipped",
                        "reason": f"Unknown step type: {step_type}",
                    })

            except Exception as e:
                steps_failed.append({
                    "type": step_type, "error": str(e),
                })

        success = len(steps_failed) == 0
        return payload.insert("response", {
            "status": "ok" if success else "partial",
            "recipe_id": recipe.get("id", "unknown"),
            "steps_done": steps_done,
            "steps_failed": steps_failed,
            "success": success,
        })


class WriteMessageFilter:
    """Write the response back via Chrome NM protocol."""

    def __init__(self, stream=None):
        self._stream = stream

    def call(self, payload: NativePayload) -> NativePayload:
        response = payload.get("response")
        request_id = payload.get("request_id", "")
        if response is None:
            response = {"error": "No handler matched"}
        msg = {"id": request_id, **response} if request_id else response
        nm_write(msg, self._stream)
        return payload.insert("sent", True)


# ── Pipeline assembly ────────────────────────────────────────────────

def build_host_pipeline(
    stream_in=None,
    stream_out=None,
    bridge_dir: Optional[str] = None,
    default_port: int = 8089,
    base_url: str = "",
) -> List:
    """Build the native host pipeline — a list of CUP-style filters.

    Returns filters in execution order.  The caller runs them sequentially
    (exactly like Pipeline.run() does internally).
    """
    return [
        ReadMessageFilter(stream=stream_in),
        RouteActionFilter(),
        PingFilter(),
        HealthFilter(default_port=default_port),
        ExecFilter(bridge_dir=bridge_dir),
        ProxyFilter(default_port=default_port),
        StartFilter(bridge_dir=bridge_dir),
        StopFilter(),
        StatusFilter(default_port=default_port, bridge_dir=bridge_dir),
        ConfigureFilter(bridge_dir=bridge_dir),
        ProvisionFilter(bridge_dir=bridge_dir, base_url=base_url),
        WriteMessageFilter(stream=stream_out),
    ]


def run_pipeline(filters: List, payload: NativePayload) -> NativePayload:
    """Run filters sequentially — CUP Pipeline.run() in miniature."""
    for f in filters:
        payload = f.call(payload)
    return payload


# ── Main loop ────────────────────────────────────────────────────────

def main():
    """Main loop — read messages from Chrome, process, respond."""
    filters = build_host_pipeline()

    # Log to stderr (Chrome captures stdout for NM protocol)
    sys.stderr.write("[cup-native-host] Started\n")
    sys.stderr.flush()

    while True:
        try:
            payload = NativePayload()
            result = run_pipeline(filters, payload)
            if result.get("action") == "eof":
                break
        except Exception as e:
            # Emergency response on crash
            try:
                nm_write({"error": f"Host crash: {e}"})
            except Exception:
                pass
            sys.stderr.write(f"[cup-native-host] Error: {e}\n")
            sys.stderr.flush()
            break

    sys.stderr.write("[cup-native-host] Exiting\n")
    sys.stderr.flush()


if __name__ == "__main__":
    main()
