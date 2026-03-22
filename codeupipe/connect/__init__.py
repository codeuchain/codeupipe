"""
Connect: Service connector wiring for codeupipe.

Provides:
- ConnectorConfig / load_connector_configs: parse [connectors] from cup.toml
- HttpConnector: built-in REST API connector (urllib, zero deps)
- discover_connectors: find + register connector packages via entry points
- check_health: pre-flight health checks on connector filters
- LocalBridge / BridgeConfig: generic browser↔desktop bridge for native compute
- discover_bridges: auto-discover localhost/LAN compute endpoints
- BridgeLauncher: auto-start native compute services
"""

from .config import ConnectorConfig, load_connector_configs, ConfigError
from .discovery import discover_connectors, check_health
from .http import HttpConnector
from .bridge_config import (
    BridgeConfig, BridgeTier, BridgeCapability,
    load_bridge_configs, BridgeConfigError,
)
from .local_bridge import LocalBridge, BridgeEndpoint, BridgeError
from .bridge_discovery import discover_bridges, scan_localhost, scan_lan, DEFAULT_PORTS
from .bridge_launcher import BridgeLauncher, LaunchResult, install_service, uninstall_service

__all__ = [
    # Connectors
    "ConnectorConfig",
    "load_connector_configs",
    "ConfigError",
    "discover_connectors",
    "check_health",
    "HttpConnector",
    # Bridge — config
    "BridgeConfig",
    "BridgeConfigError",
    "BridgeCapability",
    "BridgeTier",
    "load_bridge_configs",
    # Bridge — runtime
    "LocalBridge",
    "BridgeEndpoint",
    "BridgeError",
    # Bridge — discovery
    "discover_bridges",
    "scan_localhost",
    "scan_lan",
    "DEFAULT_PORTS",
    # Bridge — launcher
    "BridgeLauncher",
    "LaunchResult",
    "install_service",
    "uninstall_service",
]
