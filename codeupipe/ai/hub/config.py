"""Hub configuration — defines how sub-servers connect to the dock."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServerConfig:
    """Configuration for a single docked sub-server."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    tools: list[str] = field(default_factory=lambda: ["*"])
    timeout: int = 30000


@dataclass(frozen=True)
class HubConfig:
    """Configuration for the MCP hub server (the dock)."""

    servers: dict[str, ServerConfig] = field(default_factory=dict)
    hub_command: str = "python"
    hub_module: str = "codeupipe.ai.hub.server"
