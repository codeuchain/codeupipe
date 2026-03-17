"""Unit tests for CapabilityDefinition model."""

import json
from datetime import UTC

import pytest

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType

# ── CapabilityType enum ───────────────────────────────────────────────


class TestCapabilityType:
    """Tests for the CapabilityType enum."""

    def test_has_tool_type(self):
        assert CapabilityType.TOOL.value == "tool"

    def test_has_skill_type(self):
        assert CapabilityType.SKILL.value == "skill"

    def test_has_prompt_type(self):
        assert CapabilityType.PROMPT.value == "prompt"

    def test_has_resource_type(self):
        assert CapabilityType.RESOURCE.value == "resource"

    def test_is_string_enum(self):
        """CapabilityType values are usable as plain strings."""
        assert CapabilityType.TOOL == "tool"

    def test_from_string(self):
        assert CapabilityType("tool") == CapabilityType.TOOL

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            CapabilityType("not_a_type")


# ── CapabilityDefinition ──────────────────────────────────────────────


class TestCapabilityDefinition:
    """Tests for the CapabilityDefinition dataclass."""

    def test_minimal_creation(self):
        cap = CapabilityDefinition(name="echo", description="echoes input")
        assert cap.name == "echo"
        assert cap.description == "echoes input"
        assert cap.capability_type == CapabilityType.TOOL
        assert cap.server_name == ""
        assert cap.id is None
        assert cap.embedding is None

    def test_full_creation(self):
        cap = CapabilityDefinition(
            name="weather",
            description="get current weather",
            capability_type=CapabilityType.TOOL,
            server_name="weather-server",
            command="python weather.py",
            args_schema={"type": "object", "properties": {"city": {"type": "string"}}},
            metadata={"source": "builtin"},
        )
        assert cap.name == "weather"
        assert cap.capability_type == CapabilityType.TOOL
        assert cap.server_name == "weather-server"
        assert "city" in cap.args_schema["properties"]

    def test_different_types(self):
        skill = CapabilityDefinition(
            name="summarize",
            description="summarize text",
            capability_type=CapabilityType.SKILL,
        )
        assert skill.capability_type == CapabilityType.SKILL

        prompt = CapabilityDefinition(
            name="greeting",
            description="greeting template",
            capability_type=CapabilityType.PROMPT,
        )
        assert prompt.capability_type == CapabilityType.PROMPT

    def test_created_at_defaults_to_utc(self):
        cap = CapabilityDefinition(name="x", description="y")
        assert cap.created_at.tzinfo == UTC

    def test_repr(self):
        cap = CapabilityDefinition(
            name="echo",
            description="echoes input",
            server_name="echo-server",
        )
        r = repr(cap)
        assert "echo" in r
        assert "tool" in r
        assert "echo-server" in r

    # ── JSON serialisation ────────────────────────────────────────────

    def test_args_schema_json(self):
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        cap = CapabilityDefinition(name="x", description="y", args_schema=schema)
        raw = cap.args_schema_json()
        assert json.loads(raw) == schema

    def test_metadata_json(self):
        meta = {"version": 2, "tags": ["fast"]}
        cap = CapabilityDefinition(name="x", description="y", metadata=meta)
        raw = cap.metadata_json()
        assert json.loads(raw) == meta

    def test_args_schema_from_json(self):
        raw = '{"type": "object"}'
        assert CapabilityDefinition.args_schema_from_json(raw) == {"type": "object"}

    def test_args_schema_from_json_empty(self):
        assert CapabilityDefinition.args_schema_from_json("") == {}

    def test_metadata_from_json_empty(self):
        assert CapabilityDefinition.metadata_from_json("") == {}
