"""
Connector configuration — parse [connectors.*] from cup.toml.

Reads connector declarations, resolves env var references, and provides
typed config dicts to connector register functions. Zero external deps.
"""

import os
import re
from typing import Any, Dict, List, Optional

__all__ = ["ConnectorConfig", "load_connector_configs", "ConfigError"]


class ConfigError(Exception):
    """Raised when connector configuration is invalid or incomplete."""


class ConnectorConfig:
    """Parsed configuration for a single connector.

    Attributes:
        name: Connector name as declared in cup.toml (e.g. 'stripe').
        provider: Provider identifier — maps to entry point or 'http' for built-in.
        raw: The raw config dict from cup.toml (env vars NOT resolved).
    """

    def __init__(self, name: str, provider: str, raw: Dict[str, Any]):
        self.name = name
        self.provider = provider
        self.raw = dict(raw)

    def resolve_env(self, key: str, required: bool = True) -> Optional[str]:
        """Resolve an env-var reference from a config key.

        If the config value for *key* ends with ``_env``, the config value
        is treated as an environment variable name.  Otherwise the raw
        string value itself is returned.

        Args:
            key: Config key whose value references an env var
                 (e.g. ``key_env`` → looks up the env var named by its value).
            required: Raise ConfigError if the env var is unset.

        Returns:
            The resolved value, or None if not required and unset.
        """
        ref = self.raw.get(key)
        if ref is None:
            if required:
                raise ConfigError(
                    f"Connector '{self.name}': missing required config key '{key}'"
                )
            return None

        value = os.environ.get(str(ref))
        if value is None and required:
            raise ConfigError(
                f"Connector '{self.name}': env var '{ref}' (from '{key}') is not set"
            )
        return value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a raw config value."""
        return self.raw.get(key, default)

    def resolve_interpolated(self, value: str) -> str:
        """Resolve ``${VAR}`` placeholders in a string from env vars."""
        def _replace(m):
            var = m.group(1)
            val = os.environ.get(var)
            if val is None:
                raise ConfigError(
                    f"Connector '{self.name}': env var '{var}' is not set"
                )
            return val
        return re.sub(r"\$\{([^}]+)\}", _replace, value)

    def __repr__(self) -> str:
        return f"ConnectorConfig(name={self.name!r}, provider={self.provider!r})"


def load_connector_configs(manifest: Dict[str, Any]) -> List[ConnectorConfig]:
    """Extract ConnectorConfig objects from a parsed cup.toml manifest.

    Args:
        manifest: Parsed manifest dict (from load_manifest).

    Returns:
        List of ConnectorConfig, one per [connectors.*] block.
    """
    connectors_section = manifest.get("connectors", {})
    configs: List[ConnectorConfig] = []

    for name, block in connectors_section.items():
        if not isinstance(block, dict):
            raise ConfigError(
                f"[connectors.{name}] must be a table, got {type(block).__name__}"
            )
        provider = block.get("provider")
        if not provider:
            raise ConfigError(f"[connectors.{name}] missing required 'provider' key")
        configs.append(ConnectorConfig(name=name, provider=provider, raw=block))

    return configs
