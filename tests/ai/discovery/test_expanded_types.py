"""Tests for expanded CapabilityType and new fields."""

import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry


# ── New CapabilityType values ─────────────────────────────────────────


class TestNewCapabilityTypes:
    def test_instruction_type(self):
        assert CapabilityType.INSTRUCTION.value == "instruction"

    def test_plan_type(self):
        assert CapabilityType.PLAN.value == "plan"

    def test_instruction_from_string(self):
        assert CapabilityType("instruction") == CapabilityType.INSTRUCTION

    def test_plan_from_string(self):
        assert CapabilityType("plan") == CapabilityType.PLAN

    def test_all_six_types_exist(self):
        expected = {"tool", "skill", "prompt", "resource", "instruction", "plan"}
        actual = {t.value for t in CapabilityType}
        assert actual == expected


# ── source_path and content_hash fields ───────────────────────────────


class TestNewFields:
    def test_source_path_default(self):
        cap = CapabilityDefinition(name="x", description="y")
        assert cap.source_path == ""

    def test_content_hash_default(self):
        cap = CapabilityDefinition(name="x", description="y")
        assert cap.content_hash == ""

    def test_source_path_set(self):
        cap = CapabilityDefinition(
            name="skill1",
            description="a skill",
            source_path="/home/user/.copilot/skills/tdd/SKILL.md",
        )
        assert cap.source_path == "/home/user/.copilot/skills/tdd/SKILL.md"

    def test_content_hash_set(self):
        cap = CapabilityDefinition(
            name="plan1",
            description="a plan",
            content_hash="abc123def456",
        )
        assert cap.content_hash == "abc123def456"

    def test_instruction_with_source(self):
        cap = CapabilityDefinition(
            name="codeuchain_python",
            description="Python coding standards",
            capability_type=CapabilityType.INSTRUCTION,
            source_path="prompts/codeuchain_python.instructions.md",
            content_hash="sha256:abcdef",
        )
        assert cap.capability_type == CapabilityType.INSTRUCTION
        assert cap.source_path.endswith(".instructions.md")

    def test_plan_with_source(self):
        cap = CapabilityDefinition(
            name="AUTH_REFACTOR_PLAN",
            description="Auth module refactoring plan",
            capability_type=CapabilityType.PLAN,
            source_path="docs/AUTH_REFACTOR_PLAN.md",
            content_hash="sha256:fedcba",
        )
        assert cap.capability_type == CapabilityType.PLAN
        assert cap.source_path.startswith("docs/")


# ── Registry persistence of new fields ────────────────────────────────


class TestRegistryNewFields:
    @pytest.fixture
    def registry(self, tmp_path):
        db = tmp_path / "test.db"
        reg = CapabilityRegistry(db)
        yield reg
        reg.close()

    def test_insert_and_read_source_path(self, registry):
        cap = CapabilityDefinition(
            name="skill_tdd",
            description="TDD workflow",
            capability_type=CapabilityType.SKILL,
            source_path="/home/.copilot/skills/tdd/SKILL.md",
        )
        cap_id = registry.insert(cap)
        result = registry.get(cap_id)
        assert result.source_path == "/home/.copilot/skills/tdd/SKILL.md"

    def test_insert_and_read_content_hash(self, registry):
        cap = CapabilityDefinition(
            name="plan_auth",
            description="Auth plan",
            capability_type=CapabilityType.PLAN,
            content_hash="sha256:abc123",
        )
        cap_id = registry.insert(cap)
        result = registry.get(cap_id)
        assert result.content_hash == "sha256:abc123"

    def test_get_by_source_path(self, registry):
        cap = CapabilityDefinition(
            name="instr1",
            description="instruction file",
            capability_type=CapabilityType.INSTRUCTION,
            source_path="prompts/test.instructions.md",
        )
        registry.insert(cap)
        result = registry.get_by_source_path("prompts/test.instructions.md")
        assert result is not None
        assert result.name == "instr1"

    def test_get_by_source_path_nonexistent(self, registry):
        assert registry.get_by_source_path("nonexistent.md") is None

    def test_delete_by_source_path(self, registry):
        cap = CapabilityDefinition(
            name="plan1",
            description="a plan",
            source_path="docs/PLAN.md",
        )
        registry.insert(cap)
        assert registry.delete_by_source_path("docs/PLAN.md") is True
        assert registry.get_by_name("plan1") is None

    def test_delete_by_source_path_nonexistent(self, registry):
        assert registry.delete_by_source_path("nope.md") is False

    def test_list_all_instruction_type(self, registry):
        registry.insert(CapabilityDefinition(
            name="i1",
            description="instruction",
            capability_type=CapabilityType.INSTRUCTION,
        ))
        registry.insert(CapabilityDefinition(
            name="t1",
            description="tool",
            capability_type=CapabilityType.TOOL,
        ))
        instructions = registry.list_all(type_filter=CapabilityType.INSTRUCTION)
        assert len(instructions) == 1
        assert instructions[0].name == "i1"

    def test_list_all_plan_type(self, registry):
        registry.insert(CapabilityDefinition(
            name="p1",
            description="plan doc",
            capability_type=CapabilityType.PLAN,
        ))
        plans = registry.list_all(type_filter=CapabilityType.PLAN)
        assert len(plans) == 1
        assert plans[0].name == "p1"
