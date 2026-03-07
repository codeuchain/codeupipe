"""
Tests for codeupipe.connect — Ring 8: Connect.

Covers:
- ConnectorConfig parsing and env var resolution
- load_connector_configs from manifest dicts
- HttpConnector construction and Filter protocol
- Connector discovery (built-in http)
- Health check orchestration
- Manifest [connectors] validation
- CLI: cup connect --list, cup connect --health
- CLI: cup describe
- CLI: --json flag
- Top-level exports
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ── ConnectorConfig ─────────────────────────────────────────────────

class TestConnectorConfig:
    """Tests for ConnectorConfig parsing and env resolution."""

    def test_basic_creation(self):
        from codeupipe.connect.config import ConnectorConfig
        cfg = ConnectorConfig("stripe", "stripe", {"provider": "stripe", "key_env": "STRIPE_KEY"})
        assert cfg.name == "stripe"
        assert cfg.provider == "stripe"
        assert cfg.get("key_env") == "STRIPE_KEY"

    def test_resolve_env_success(self, monkeypatch):
        from codeupipe.connect.config import ConnectorConfig
        monkeypatch.setenv("MY_API_KEY", "sk-test-123")
        cfg = ConnectorConfig("test", "test", {"key_env": "MY_API_KEY"})
        assert cfg.resolve_env("key_env") == "sk-test-123"

    def test_resolve_env_missing_raises(self):
        from codeupipe.connect.config import ConnectorConfig, ConfigError
        cfg = ConnectorConfig("test", "test", {"key_env": "NONEXISTENT_VAR_12345"})
        with pytest.raises(ConfigError, match="not set"):
            cfg.resolve_env("key_env")

    def test_resolve_env_missing_optional(self):
        from codeupipe.connect.config import ConnectorConfig
        cfg = ConnectorConfig("test", "test", {"key_env": "NONEXISTENT_VAR_12345"})
        assert cfg.resolve_env("key_env", required=False) is None

    def test_resolve_env_missing_key_raises(self):
        from codeupipe.connect.config import ConnectorConfig, ConfigError
        cfg = ConnectorConfig("test", "test", {})
        with pytest.raises(ConfigError, match="missing required"):
            cfg.resolve_env("key_env")

    def test_resolve_interpolated(self, monkeypatch):
        from codeupipe.connect.config import ConnectorConfig
        monkeypatch.setenv("TOKEN", "abc123")
        cfg = ConnectorConfig("test", "test", {})
        assert cfg.resolve_interpolated("Bearer ${TOKEN}") == "Bearer abc123"

    def test_resolve_interpolated_missing_raises(self):
        from codeupipe.connect.config import ConnectorConfig, ConfigError
        cfg = ConnectorConfig("test", "test", {})
        with pytest.raises(ConfigError, match="not set"):
            cfg.resolve_interpolated("Bearer ${MISSING_VAR_XYZ}")

    def test_get_default(self):
        from codeupipe.connect.config import ConnectorConfig
        cfg = ConnectorConfig("test", "test", {})
        assert cfg.get("missing", "default") == "default"

    def test_repr(self):
        from codeupipe.connect.config import ConnectorConfig
        cfg = ConnectorConfig("my-api", "http", {})
        assert "my-api" in repr(cfg)
        assert "http" in repr(cfg)


# ── load_connector_configs ──────────────────────────────────────────

class TestLoadConnectorConfigs:
    """Tests for parsing [connectors] section from manifests."""

    def test_empty_manifest(self):
        from codeupipe.connect.config import load_connector_configs
        configs = load_connector_configs({"project": {"name": "test"}})
        assert configs == []

    def test_single_connector(self):
        from codeupipe.connect.config import load_connector_configs
        manifest = {
            "project": {"name": "test"},
            "connectors": {
                "stripe": {"provider": "stripe", "key_env": "STRIPE_KEY"},
            },
        }
        configs = load_connector_configs(manifest)
        assert len(configs) == 1
        assert configs[0].name == "stripe"
        assert configs[0].provider == "stripe"

    def test_multiple_connectors(self):
        from codeupipe.connect.config import load_connector_configs
        manifest = {
            "connectors": {
                "stripe": {"provider": "stripe"},
                "openai": {"provider": "openai"},
                "webhook": {"provider": "http", "base_url": "https://example.com"},
            },
        }
        configs = load_connector_configs(manifest)
        assert len(configs) == 3
        names = {c.name for c in configs}
        assert names == {"stripe", "openai", "webhook"}

    def test_missing_provider_raises(self):
        from codeupipe.connect.config import load_connector_configs, ConfigError
        manifest = {"connectors": {"bad": {"key_env": "X"}}}
        with pytest.raises(ConfigError, match="provider"):
            load_connector_configs(manifest)

    def test_non_table_raises(self):
        from codeupipe.connect.config import load_connector_configs, ConfigError
        manifest = {"connectors": {"bad": "not a table"}}
        with pytest.raises(ConfigError, match="must be a table"):
            load_connector_configs(manifest)


# ── HttpConnector ───────────────────────────────────────────────────

class TestHttpConnector:
    """Tests for the built-in HTTP connector Filter."""

    def test_creation(self):
        from codeupipe.connect.http import HttpConnector
        c = HttpConnector("https://api.example.com", method="POST")
        assert c.base_url == "https://api.example.com"
        assert c.method == "POST"

    def test_from_config_with_base_url(self):
        from codeupipe.connect.config import ConnectorConfig
        from codeupipe.connect.http import HttpConnector
        cfg = ConnectorConfig("test", "http", {
            "provider": "http",
            "base_url": "https://example.com/api",
            "method": "POST",
        })
        c = HttpConnector.from_config(cfg)
        assert c.base_url == "https://example.com/api"
        assert c.method == "POST"

    def test_from_config_with_env(self, monkeypatch):
        from codeupipe.connect.config import ConnectorConfig
        from codeupipe.connect.http import HttpConnector
        monkeypatch.setenv("TEST_URL", "https://env.example.com")
        cfg = ConnectorConfig("test", "http", {
            "provider": "http",
            "base_url_env": "TEST_URL",
        })
        c = HttpConnector.from_config(cfg)
        assert c.base_url == "https://env.example.com"

    def test_from_config_missing_url_raises(self):
        from codeupipe.connect.config import ConnectorConfig, ConfigError
        from codeupipe.connect.http import HttpConnector
        cfg = ConnectorConfig("test", "http", {"provider": "http"})
        with pytest.raises(ConfigError, match="base_url"):
            HttpConnector.from_config(cfg)

    def test_from_config_headers_interpolation(self, monkeypatch):
        from codeupipe.connect.config import ConnectorConfig
        from codeupipe.connect.http import HttpConnector
        monkeypatch.setenv("MY_TOKEN", "secret123")
        cfg = ConnectorConfig("test", "http", {
            "provider": "http",
            "base_url": "https://example.com",
            "headers": {"Authorization": "Bearer ${MY_TOKEN}"},
        })
        c = HttpConnector.from_config(cfg)
        assert c.headers["Authorization"] == "Bearer secret123"

    def test_repr(self):
        from codeupipe.connect.http import HttpConnector
        c = HttpConnector("https://example.com", method="GET")
        assert "https://example.com" in repr(c)
        assert "GET" in repr(c)

    @pytest.mark.asyncio
    async def test_call_protocol(self):
        """HttpConnector implements the Filter async call protocol."""
        from codeupipe.connect.http import HttpConnector
        c = HttpConnector("https://httpbin.org/status/418")
        # We don't actually call the network — just verify the method exists
        assert hasattr(c, "call")
        import inspect
        assert inspect.iscoroutinefunction(c.call)

    @pytest.mark.asyncio
    async def test_health_protocol(self):
        """HttpConnector implements the health check convention."""
        from codeupipe.connect.http import HttpConnector
        c = HttpConnector("https://httpbin.org")
        assert hasattr(c, "health")
        import inspect
        assert inspect.iscoroutinefunction(c.health)


# ── Discovery ───────────────────────────────────────────────────────

class TestDiscovery:
    """Tests for connector discovery and registration."""

    def test_discover_http_builtin(self, monkeypatch):
        from codeupipe.connect.config import ConnectorConfig
        from codeupipe.connect.discovery import discover_connectors
        from codeupipe.registry import Registry

        monkeypatch.setenv("TEST_BASE_URL", "https://example.com")
        reg = Registry()
        configs = [
            ConnectorConfig("my-api", "http", {
                "provider": "http",
                "base_url_env": "TEST_BASE_URL",
            })
        ]
        result = discover_connectors(configs, reg)
        assert "http" in result
        assert "my-api" in result["http"]
        assert reg.has("my-api")

    def test_discover_unknown_provider_skipped(self):
        from codeupipe.connect.config import ConnectorConfig
        from codeupipe.connect.discovery import discover_connectors
        from codeupipe.registry import Registry

        reg = Registry()
        configs = [
            ConnectorConfig("unknown-svc", "nonexistent-provider-xyz", {
                "provider": "nonexistent-provider-xyz",
            })
        ]
        result = discover_connectors(configs, reg)
        assert "nonexistent-provider-xyz" not in result
        assert not reg.has("unknown-svc")

    def test_discover_empty(self):
        from codeupipe.connect.discovery import discover_connectors
        from codeupipe.registry import Registry
        reg = Registry()
        result = discover_connectors([], reg)
        assert result == {}


# ── Health Checks ───────────────────────────────────────────────────

class TestHealthChecks:
    """Tests for health check orchestration."""

    def test_health_no_connectors(self):
        from codeupipe.connect.discovery import check_health
        from codeupipe.registry import Registry
        reg = Registry()
        results = check_health(reg)
        assert results == {}

    def test_health_no_method_assumed_healthy(self, monkeypatch):
        from codeupipe.connect.discovery import check_health
        from codeupipe.registry import Registry

        class SimpleFilter:
            async def call(self, payload):
                return payload

        reg = Registry()
        reg.register("simple", SimpleFilter, kind="connector")
        results = check_health(reg, ["simple"])
        assert results["simple"] is True

    def test_health_sync_method(self):
        from codeupipe.connect.discovery import check_health
        from codeupipe.registry import Registry

        class HealthyFilter:
            async def call(self, payload):
                return payload
            def health(self):
                return True

        reg = Registry()
        reg.register("healthy", HealthyFilter, kind="connector")
        results = check_health(reg, ["healthy"])
        assert results["healthy"] is True

    def test_health_failing_method(self):
        from codeupipe.connect.discovery import check_health
        from codeupipe.registry import Registry

        class UnhealthyFilter:
            async def call(self, payload):
                return payload
            def health(self):
                return False

        reg = Registry()
        reg.register("unhealthy", UnhealthyFilter, kind="connector")
        results = check_health(reg, ["unhealthy"])
        assert results["unhealthy"] is False

    def test_health_exception_is_false(self):
        from codeupipe.connect.discovery import check_health
        from codeupipe.registry import Registry

        class BrokenFilter:
            async def call(self, payload):
                return payload
            def health(self):
                raise RuntimeError("connection refused")

        reg = Registry()
        reg.register("broken", BrokenFilter, kind="connector")
        results = check_health(reg, ["broken"])
        assert results["broken"] is False


# ── Manifest [connectors] Validation ────────────────────────────────

class TestManifestConnectors:
    """Tests for [connectors] validation in cup.toml."""

    def test_valid_connectors(self, tmp_path):
        from codeupipe.deploy.manifest import load_manifest
        content = (
            '[project]\nname = "test"\nversion = "0.1.0"\n\n'
            '[connectors.stripe]\nprovider = "stripe"\nkey_env = "SK"\n\n'
            '[connectors.webhook]\nprovider = "http"\nbase_url = "https://x.com"\n\n'
            '[dependencies]\ncodeupipe = ">=0.8.0"\n'
        )
        f = tmp_path / "cup.toml"
        f.write_text(content)
        m = load_manifest(f)
        assert "connectors" in m
        assert "stripe" in m["connectors"]

    def test_connector_missing_provider(self, tmp_path):
        from codeupipe.deploy.manifest import load_manifest, ManifestError
        content = (
            '[project]\nname = "test"\nversion = "0.1.0"\n\n'
            '[connectors.bad]\nkey_env = "X"\n'
        )
        f = tmp_path / "cup.toml"
        f.write_text(content)
        with pytest.raises(ManifestError, match="provider"):
            load_manifest(f)

    def test_connector_non_table(self, tmp_path):
        from codeupipe.deploy.manifest import load_manifest, ManifestError
        content = (
            '[project]\nname = "test"\nversion = "0.1.0"\n\n'
            '[connectors]\nbad = "string"\n'
        )
        f = tmp_path / "cup.toml"
        f.write_text(content)
        with pytest.raises(ManifestError, match="must be a table"):
            load_manifest(f)


# ── CLI: cup connect ────────────────────────────────────────────────

class TestCLIConnect:
    """Tests for cup connect CLI commands."""

    def test_connect_list_no_manifest(self, tmp_path, monkeypatch):
        from codeupipe.cli import main
        monkeypatch.chdir(tmp_path)
        result = main(["connect", "--list"])
        assert result == 0

    def test_connect_list_with_connectors(self, tmp_path, monkeypatch):
        from codeupipe.cli import main
        monkeypatch.chdir(tmp_path)
        content = (
            '[project]\nname = "test"\nversion = "0.1.0"\n\n'
            '[connectors.stripe]\nprovider = "stripe"\n\n'
            '[connectors.webhook]\nprovider = "http"\nbase_url = "https://x.com"\n'
        )
        (tmp_path / "cup.toml").write_text(content)
        result = main(["connect", "--list"])
        assert result == 0

    def test_connect_list_json(self, tmp_path, monkeypatch, capsys):
        from codeupipe.cli import main
        monkeypatch.chdir(tmp_path)
        content = (
            '[project]\nname = "test"\nversion = "0.1.0"\n\n'
            '[connectors.stripe]\nprovider = "stripe"\n'
        )
        (tmp_path / "cup.toml").write_text(content)
        result = main(["--json", "connect", "--list"])
        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "connectors" in data
        assert data["connectors"][0]["name"] == "stripe"

    def test_connect_health_no_manifest(self, tmp_path, monkeypatch):
        from codeupipe.cli import main
        monkeypatch.chdir(tmp_path)
        result = main(["connect", "--health"])
        assert result == 1  # Missing manifest

    def test_connect_no_flags_shows_usage(self, tmp_path, monkeypatch):
        from codeupipe.cli import main
        monkeypatch.chdir(tmp_path)
        result = main(["connect"])
        assert result == 1


# ── CLI: cup describe ───────────────────────────────────────────────

class TestCLIDescribe:
    """Tests for cup describe CLI command."""

    def test_describe_basic(self, tmp_path):
        from codeupipe.cli import main
        config = {
            "pipeline": {
                "name": "ai-chat",
                "steps": [
                    {"name": "SanitizeInput", "type": "filter"},
                    {"name": "OpenAIChat", "type": "filter"},
                    {"name": "FormatResponse", "type": "filter"},
                ],
                "require_input": ["message"],
                "guarantee_output": ["response"],
            }
        }
        f = tmp_path / "pipeline.json"
        f.write_text(json.dumps(config))
        result = main(["describe", str(f)])
        assert result == 0

    def test_describe_json(self, tmp_path, capsys):
        from codeupipe.cli import main
        config = {
            "pipeline": {
                "name": "test-pipe",
                "steps": [
                    {"name": "Step1", "type": "filter"},
                    {"name": "Step2", "type": "tap"},
                ],
                "require_input": ["input_key"],
                "guarantee_output": ["output_key"],
            }
        }
        f = tmp_path / "pipe.json"
        f.write_text(json.dumps(config))
        result = main(["--json", "describe", str(f)])
        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["name"] == "test-pipe"
        assert len(data["steps"]) == 2
        assert data["require_input"] == ["input_key"]
        assert data["guarantee_output"] == ["output_key"]

    def test_describe_missing_file(self, tmp_path):
        from codeupipe.cli import main
        result = main(["describe", str(tmp_path / "nonexistent.json")])
        assert result == 1

    def test_describe_invalid_json(self, tmp_path):
        from codeupipe.cli import main
        f = tmp_path / "bad.json"
        f.write_text("not json at all {{{")
        result = main(["describe", str(f)])
        assert result == 1

    def test_describe_empty_pipeline(self, tmp_path, capsys):
        from codeupipe.cli import main
        f = tmp_path / "empty.json"
        f.write_text(json.dumps({"pipeline": {"name": "empty", "steps": []}}))
        result = main(["--json", "describe", str(f)])
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["steps"] == []


# ── CLI: --json flag ────────────────────────────────────────────────

class TestCLIJsonFlag:
    """Tests for the global --json flag."""

    def test_json_flag_parsed(self):
        """The --json flag is accepted without error."""
        from codeupipe.cli import main
        # --json with --list (a command that doesn't need files)
        result = main(["--json", "list"])
        assert result == 0

    def test_connect_list_json_no_manifest(self, tmp_path, monkeypatch, capsys):
        from codeupipe.cli import main
        monkeypatch.chdir(tmp_path)
        result = main(["--json", "connect", "--list"])
        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "connectors" in data


# ── Exports ─────────────────────────────────────────────────────────

class TestExportsRing8:
    """Verify Ring 8 types are accessible from top-level."""

    def test_connect_exports(self):
        from codeupipe import (
            ConnectorConfig, load_connector_configs, ConfigError,
            discover_connectors, check_health, HttpConnector,
        )
        assert ConnectorConfig is not None
        assert callable(load_connector_configs)
        assert callable(discover_connectors)
        assert callable(check_health)
        assert HttpConnector is not None
