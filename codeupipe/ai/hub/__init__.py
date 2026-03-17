"""MCP Hub Server — the dock for sub-servers.

Exports:
    ServerRegistry  — tracks docked MCP sub-servers and tool routing
    HubIOWrapper    — coordinates hub I/O around the agent loop
    ServerConfig    — configuration for a single docked sub-server
    HubConfig       — configuration for the hub server
"""

from codeupipe.ai.hub.config import HubConfig, ServerConfig
from codeupipe.ai.hub.io_wrapper import HubIOWrapper
from codeupipe.ai.hub.registry import ServerRegistry

__all__ = [
    "HubConfig",
    "HubIOWrapper",
    "ServerConfig",
    "ServerRegistry",
]
