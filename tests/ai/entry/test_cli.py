"""Tests for ``cup ai-*`` CLI argument parsing and handler wiring."""

import argparse

import pytest

from codeupipe.cli._registry import CommandRegistry
from codeupipe.cli.commands.ai_cmds import setup


def _build_parser():
    """Build a minimal parser with ai_cmds registered."""
    reg = CommandRegistry()
    parser = argparse.ArgumentParser(prog="cup")
    sub = parser.add_subparsers(dest="command")
    setup(sub, reg)
    return parser, reg


@pytest.mark.unit
class TestAiAskArgs:
    """Unit tests for ``cup ai-ask`` argument parsing."""

    def test_parse_prompt(self):
        """Parses the positional prompt."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-ask", "hello"])
        assert args.prompt == "hello"

    def test_default_model(self):
        """Default model is gpt-4.1."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-ask", "hello"])
        assert args.model == "gpt-4.1"

    def test_custom_model(self):
        """Parses --model flag."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-ask", "hello", "--model", "gpt-5"])
        assert args.model == "gpt-5"

    def test_verbose_flag(self):
        """Parses --verbose flag."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-ask", "hello", "-v"])
        assert args.verbose is True

    def test_no_verbose_by_default(self):
        """Verbose is False by default."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-ask", "hello"])
        assert args.verbose is False

    def test_json_flag(self):
        """Parses --json flag."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-ask", "hello", "--json"])
        assert args.json_output is True


@pytest.mark.unit
class TestAiInteractiveArgs:
    """Unit tests for ``cup ai-interactive`` argument parsing."""

    def test_interactive_default_model(self):
        """Default model is gpt-4.1."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-interactive"])
        assert args.model == "gpt-4.1"

    def test_interactive_custom_model(self):
        """Can specify model with interactive."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-interactive", "--model", "gpt-4.1"])
        assert args.model == "gpt-4.1"

    def test_interactive_verbose(self):
        """Can enable verbose in interactive mode."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-interactive", "--verbose"])
        assert args.verbose is True


@pytest.mark.unit
class TestAiDiscoverArgs:
    """Unit tests for ``cup ai-discover`` argument parsing."""

    def test_parse_intent(self):
        """Parses the positional intent."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-discover", "calculate sums"])
        assert args.intent == "calculate sums"

    def test_discover_json(self):
        """Parses --json flag."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-discover", "find tools", "--json"])
        assert args.json_output is True


@pytest.mark.unit
class TestAiRegisterArgs:
    """Unit tests for ``cup ai-register`` argument parsing."""

    def test_register_requires_server_name(self):
        """--server-name is required."""
        parser, _ = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["ai-register"])

    def test_register_server_url(self):
        """Parses --server-url."""
        parser, _ = _build_parser()
        args = parser.parse_args([
            "ai-register", "--server-name", "echo",
            "--server-url", "http://localhost:3000",
        ])
        assert args.server_name == "echo"
        assert args.server_url == "http://localhost:3000"

    def test_register_server_command(self):
        """Parses --server-command."""
        parser, _ = _build_parser()
        args = parser.parse_args([
            "ai-register", "--server-name", "echo",
            "--server-command", "python", "--server-args", "server.py",
        ])
        assert args.server_name == "echo"
        assert args.server_command == "python"
        assert args.server_args == ["server.py"]


@pytest.mark.unit
class TestCommandRegistration:
    """Verify all AI commands are registered in the CommandRegistry."""

    def test_all_ai_commands_registered(self):
        """All 7 ai-* commands are registered."""
        _, reg = _build_parser()
        expected = {
            "ai-ask", "ai-interactive", "ai-tui",
            "ai-discover", "ai-sync", "ai-register", "ai-hub",
        }
        assert expected.issubset(reg.commands)
