"""Tests for ``cup ai-interactive`` argument parsing."""

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
class TestInteractiveModeArgParsing:
    """Test that interactive arguments are parsed correctly."""

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

    def test_interactive_default_not_verbose(self):
        """Verbose is False by default."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-interactive"])
        assert args.verbose is False


@pytest.mark.unit
class TestTuiModeArgParsing:
    """Test that TUI arguments are parsed correctly."""

    def test_tui_default_model(self):
        """Default model is gpt-4.1."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-tui"])
        assert args.model == "gpt-4.1"

    def test_tui_custom_model(self):
        """Can specify model with TUI."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-tui", "--model", "gpt-5"])
        assert args.model == "gpt-5"

    def test_tui_verbose(self):
        """Can enable verbose in TUI mode."""
        parser, _ = _build_parser()
        args = parser.parse_args(["ai-tui", "-v"])
        assert args.verbose is True
