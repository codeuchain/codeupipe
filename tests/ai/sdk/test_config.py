"""Tests for AgentConfig — SDK configuration object."""

import pytest
from pathlib import Path


class TestAgentConfig:
    """AgentConfig provides sensible defaults and customization."""

    def test_default_config(self):
        """Config has sensible defaults out of the box."""
        from codeupipe.ai.agent.config import AgentConfig

        cfg = AgentConfig()
        assert cfg.model == "gpt-4.1"
        assert cfg.max_iterations == 10
        assert cfg.verbose is False
        assert cfg.auto_discover is True

    def test_custom_model(self):
        """Model can be overridden."""
        from codeupipe.ai.agent.config import AgentConfig

        cfg = AgentConfig(model="claude-sonnet-4")
        assert cfg.model == "claude-sonnet-4"

    def test_custom_max_iterations(self):
        """Max iterations cap is configurable."""
        from codeupipe.ai.agent.config import AgentConfig

        cfg = AgentConfig(max_iterations=25)
        assert cfg.max_iterations == 25

    def test_verbose_flag(self):
        """Verbose flag enables detail-level events."""
        from codeupipe.ai.agent.config import AgentConfig

        cfg = AgentConfig(verbose=True)
        assert cfg.verbose is True

    def test_event_types_filter(self):
        """Can filter to specific event types only."""
        from codeupipe.ai.agent.config import AgentConfig
        from codeupipe.ai.agent.events import EventType

        cfg = AgentConfig(event_types={EventType.DONE, EventType.ERROR})
        assert cfg.event_types == {EventType.DONE, EventType.ERROR}

    def test_event_types_default_none(self):
        """Default event_types is None (all events pass through)."""
        from codeupipe.ai.agent.config import AgentConfig

        cfg = AgentConfig()
        assert cfg.event_types is None

    def test_servers_dict(self):
        """Custom MCP servers can be defined."""
        from codeupipe.ai.agent.config import AgentConfig, ServerDef

        cfg = AgentConfig(
            servers={
                "my_server": ServerDef(
                    command="python",
                    args=["-m", "my_module"],
                ),
            }
        )
        assert "my_server" in cfg.servers
        assert cfg.servers["my_server"].command == "python"

    def test_servers_default_none(self):
        """Default servers is None (use built-in hub)."""
        from codeupipe.ai.agent.config import AgentConfig

        cfg = AgentConfig()
        assert cfg.servers is None

    def test_registry_path(self):
        """Custom registry path can be set."""
        from codeupipe.ai.agent.config import AgentConfig

        cfg = AgentConfig(registry_path=Path("/tmp/test.db"))
        assert cfg.registry_path == Path("/tmp/test.db")

    def test_auto_discover_disabled(self):
        """Auto-discovery can be turned off."""
        from codeupipe.ai.agent.config import AgentConfig

        cfg = AgentConfig(auto_discover=False)
        assert cfg.auto_discover is False

    def test_session_id(self):
        """Session ID can be set for conversation continuity."""
        from codeupipe.ai.agent.config import AgentConfig

        cfg = AgentConfig(session_id="abc-123")
        assert cfg.session_id == "abc-123"

    def test_session_id_default_none(self):
        """Session ID defaults to None (new session each run)."""
        from codeupipe.ai.agent.config import AgentConfig

        cfg = AgentConfig()
        assert cfg.session_id is None


class TestServerDef:
    """ServerDef defines an MCP server connection."""

    def test_stdio_server(self):
        """Stdio server defined by command + args."""
        from codeupipe.ai.agent.config import ServerDef

        s = ServerDef(command="python", args=["-m", "my_server"])
        assert s.command == "python"
        assert s.args == ["-m", "my_server"]
        assert s.url is None

    def test_sse_server(self):
        """SSE server defined by URL."""
        from codeupipe.ai.agent.config import ServerDef

        s = ServerDef(url="http://localhost:8080/sse")
        assert s.url == "http://localhost:8080/sse"
        assert s.command is None

    def test_server_needs_command_or_url(self):
        """Server must have at least command or url."""
        from codeupipe.ai.agent.config import ServerDef

        # Both None — should be allowed at creation but semantically
        # invalid (Agent will catch this at start())
        s = ServerDef()
        assert s.command is None
        assert s.url is None
