"""
Connect: Service connector wiring for codeupipe.

Provides:
- ConnectorConfig / load_connector_configs: parse [connectors] from cup.toml
- HttpConnector: built-in REST API connector (urllib, zero deps)
- discover_connectors: find + register connector packages via entry points
- check_health: pre-flight health checks on connector filters
"""

from .config import ConnectorConfig, load_connector_configs, ConfigError
from .discovery import discover_connectors, check_health
from .http import HttpConnector

__all__ = [
    "ConnectorConfig",
    "load_connector_configs",
    "ConfigError",
    "discover_connectors",
    "check_health",
    "HttpConnector",
]
