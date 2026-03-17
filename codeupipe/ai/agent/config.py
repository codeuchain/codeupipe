"""AgentConfig and ServerDef — SDK configuration objects.

AgentConfig is the single knob consumers turn to customize agent
behavior. Everything has sensible defaults — you can create an
Agent with no config at all.

ServerDef describes an MCP server connection (stdio or SSE).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from codeupipe.ai.agent.events import EventType


@dataclass
class ServerDef:
    """Definition for an MCP server connection.

    Attributes:
        command: Command to run (stdio transport).
        args: Arguments for the command.
        url: URL for SSE transport.
    """

    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None


@dataclass
class AgentConfig:
    """Configuration for an Agent instance.

    All fields have sensible defaults. Pass only what you want to override.

    Attributes:
        model: Language model to use.
        max_iterations: Safety cap for loop iterations.
        verbose: Whether to emit detail-level events (tool calls, state changes).
        auto_discover: Whether to run capability discovery from prompt intent.
        event_types: If set, only yield events of these types.
        servers: Custom MCP server definitions (overrides default hub).
        registry_path: Path to capability registry database.
        skills_paths: Directories to scan for skill files.
        session_id: Session identifier for conversation continuity.
    """

    model: str = "gpt-4.1"
    max_iterations: int = 10
    verbose: bool = False
    auto_discover: bool = True
    event_types: set[EventType] | None = None
    servers: dict[str, ServerDef] | None = None
    registry_path: Path | None = None
    skills_paths: list[Path] | None = None
    session_id: str | None = None
