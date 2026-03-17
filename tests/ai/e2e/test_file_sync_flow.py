"""E2E test: File Sync -> Discover flow.

Exercises the full file-based lifecycle:
  1. Create temp filesystem with skills, instructions, plans
  2. Sync local sources via FileRegistrationChain
  3. Discover capabilities by intent via IntentDiscoveryChain
  4. Verify grouped results include all capability types
  5. Re-sync after file changes and verify delta detection

Uses mocked embeddings (no real model download) but real SQLite,
real filesystem, and real chain orchestration.
"""

from contextlib import contextmanager
from unittest.mock import patch

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.pipelines.file_registration import (
    build_file_registration_chain,
)
from codeupipe.ai.pipelines.intent_discovery import (
    build_intent_discovery_chain,
)
from codeupipe.ai.config import reset_settings
from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder
from codeupipe.ai.discovery.models import CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry


# -- Embedding fakes ------------------------------------------------

# Domain vectors with distinctive regions for each type
DOMAIN_VECTORS = {
    "coding": (0, 100),
    "testing": (100, 200),
    "architecture": (200, 300),
    "style": (300, 400),
}

_CODING_KW = ["coding", "code", "generate", "implement", "write"]
_TESTING_KW = ["testing", "test", "tdd", "verify", "assert"]
_ARCH_KW = ["architecture", "design", "pattern", "structure", "roadmap", "plan"]
_STYLE_KW = ["style", "format", "lint", "pep", "convention", "instruction"]


def _domain_embedding(text: str) -> np.ndarray:
    """Fake embedding with semantic domain separation."""
    vec = np.zeros(1024, dtype=np.float32)
    low = text.lower()

    if any(w in low for w in _CODING_KW):
        s, e = DOMAIN_VECTORS["coding"]
        vec[s:e] = 1.0
    elif any(w in low for w in _TESTING_KW):
        s, e = DOMAIN_VECTORS["testing"]
        vec[s:e] = 1.0
    elif any(w in low for w in _ARCH_KW):
        s, e = DOMAIN_VECTORS["architecture"]
        vec[s:e] = 1.0
    elif any(w in low for w in _STYLE_KW):
        s, e = DOMAIN_VECTORS["style"]
        vec[s:e] = 1.0
    else:
        vec[:50] = 0.1

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


@contextmanager
def _patch_embedder():
    """Patch SnowflakeArcticEmbedder init + methods."""
    with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
         patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_domain_embedding), \
         patch.object(SnowflakeArcticEmbedder, "embed_query", side_effect=_domain_embedding):
        yield


@pytest.fixture(autouse=True)
def _clean():
    SnowflakeArcticEmbedder.reset()
    reset_settings()
    yield
    SnowflakeArcticEmbedder.reset()
    reset_settings()


@pytest.fixture
def fresh_registry(tmp_path):
    """Create a fresh SQLite registry."""
    db = tmp_path / "e2e_file_test.db"
    return CapabilityRegistry(db)


@pytest.fixture
def project_fs(tmp_path):
    """Create a project filesystem with skills, instructions, and plans."""
    # Skills
    skills = tmp_path / "skills"
    coding = skills / "coding"
    coding.mkdir(parents=True)
    (coding / "SKILL.md").write_text(
        "---\n"
        "name: coding\n"
        "description: Code generation and implementation skill\n"
        "---\n\n"
        "# Coding Skill\n\n"
        "Generate and write code.\n"
    )

    tdd = skills / "tdd-workflow"
    tdd.mkdir()
    (tdd / "SKILL.md").write_text(
        "---\n"
        "name: tdd-workflow\n"
        "description: Test driven development workflow with verify and assert\n"
        "---\n\n"
        "# TDD Workflow\n\n"
        "RED -> GREEN -> REFACTOR\n"
    )

    # Instructions
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "codestyle.instructions.md").write_text(
        "---\n"
        "applyTo: '**/*.py'\n"
        "---\n\n"
        "# Code Style Convention\n\n"
        "Follow PEP 8 format and lint rules.\n"
    )

    # Plans
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text(
        "# Architecture Design Pattern\n\n"
        "## Structure\n\n"
        "Layered architecture with clear boundaries.\n"
    )

    return tmp_path


@pytest.mark.e2e
class TestFileSyncDiscoveryFlow:
    """End-to-end: sync local files -> discover by intent."""

    @pytest.mark.asyncio
    async def test_sync_registers_all_types(self, fresh_registry, project_fs):
        """Should register skills, instructions, and plans from filesystem."""
        with _patch_embedder():
            chain = build_file_registration_chain()
            ctx = Payload({
                "skills_paths": [project_fs / "skills"],
                "instructions_paths": [project_fs / "prompts"],
                "plans_paths": [project_fs / "docs"],
                "project_root": project_fs,
                "capability_registry": fresh_registry,
            })
            result = await chain.run(ctx)

            assert result.get("registered_count") == 4  # 2 skills + 1 instr + 1 plan

            all_caps = fresh_registry.list_all()
            types = {c.capability_type for c in all_caps}
            assert CapabilityType.SKILL in types
            assert CapabilityType.INSTRUCTION in types
            assert CapabilityType.PLAN in types

    @pytest.mark.asyncio
    async def test_sync_then_discover_coding(self, fresh_registry, project_fs):
        """Sync files, discover 'generate code' -> coding skill."""
        with _patch_embedder():
            # Sync
            sync_chain = build_file_registration_chain()
            await sync_chain.run(Payload({
                "skills_paths": [project_fs / "skills"],
                "instructions_paths": [project_fs / "prompts"],
                "plans_paths": [project_fs / "docs"],
                "project_root": project_fs,
                "capability_registry": fresh_registry,
            }))

            # Discover
            disc_chain = build_intent_discovery_chain()
            result = await disc_chain.run(Payload({
                "intent": "generate and implement code",
                "capability_registry": fresh_registry,
            }))

            capabilities = result.get("capabilities")
            assert len(capabilities) > 0
            names = [c.name for c in capabilities]
            assert "coding" in names

    @pytest.mark.asyncio
    async def test_discover_returns_grouped_results(self, fresh_registry, project_fs):
        """Discovery should return grouped_capabilities by type."""
        with _patch_embedder():
            # Sync all
            sync_chain = build_file_registration_chain()
            await sync_chain.run(Payload({
                "skills_paths": [project_fs / "skills"],
                "instructions_paths": [project_fs / "prompts"],
                "plans_paths": [project_fs / "docs"],
                "project_root": project_fs,
                "capability_registry": fresh_registry,
            }))

            # Discover with broad query matching architecture
            disc_chain = build_intent_discovery_chain()
            result = await disc_chain.run(Payload({
                "intent": "architecture design pattern structure",
                "capability_registry": fresh_registry,
            }))

            grouped = result.get("grouped_capabilities")
            assert grouped is not None
            # Should have all type keys
            for cap_type in CapabilityType:
                assert cap_type.value in grouped

    @pytest.mark.asyncio
    async def test_resync_detects_changes(self, fresh_registry, project_fs):
        """Second sync should detect modified files."""
        with _patch_embedder():
            chain = build_file_registration_chain()
            ctx_data = {
                "skills_paths": [project_fs / "skills"],
                "instructions_paths": [project_fs / "prompts"],
                "plans_paths": [project_fs / "docs"],
                "project_root": project_fs,
                "capability_registry": fresh_registry,
            }

            # First sync
            result1 = await chain.run(Payload(ctx_data))
            assert result1.get("registered_count") == 4

            # Modify the coding skill
            skill_file = project_fs / "skills" / "coding" / "SKILL.md"
            skill_file.write_text(
                "---\n"
                "name: coding\n"
                "description: Updated code generation skill v2\n"
                "---\n\n"
                "# Coding v2\n"
            )

            # Second sync — should detect the change
            result2 = await chain.run(Payload(ctx_data))
            stats = result2.get("sync_stats")
            assert stats["updated"] == 1
            assert stats["unchanged"] == 3

    @pytest.mark.asyncio
    async def test_resync_removes_deleted_files(self, fresh_registry, project_fs):
        """Sync should remove stale entries when files are deleted."""
        with _patch_embedder():
            chain = build_file_registration_chain()
            ctx_data = {
                "skills_paths": [project_fs / "skills"],
                "instructions_paths": [project_fs / "prompts"],
                "plans_paths": [project_fs / "docs"],
                "project_root": project_fs,
                "capability_registry": fresh_registry,
            }

            # First sync
            await chain.run(Payload(ctx_data))
            assert len(fresh_registry.list_all()) == 4

            # Delete the architecture plan
            (project_fs / "docs" / "ARCHITECTURE.md").unlink()

            # Second sync
            result = await chain.run(Payload(ctx_data))
            stats = result.get("sync_stats")
            assert stats["removed"] == 1
            assert len(fresh_registry.list_all()) == 3

    @pytest.mark.asyncio
    async def test_mixed_server_and_file_registration(self, fresh_registry, project_fs):
        """Server tools and file capabilities coexist in registry."""
        from codeupipe.ai.pipelines.capability_registration import (
            build_capability_registration_chain,
        )

        with _patch_embedder():
            # Register server tools
            reg_chain = build_capability_registration_chain()
            await reg_chain.run(Payload({
                "server_name": "math-server",
                "server_tools": [
                    {"name": "add_numbers", "description": "adds numbers to calculate sum"},
                ],
                "capability_registry": fresh_registry,
            }))

            # Sync local files
            sync_chain = build_file_registration_chain()
            await sync_chain.run(Payload({
                "skills_paths": [project_fs / "skills"],
                "instructions_paths": [project_fs / "prompts"],
                "plans_paths": [project_fs / "docs"],
                "project_root": project_fs,
                "capability_registry": fresh_registry,
            }))

            # Registry should have both
            all_caps = fresh_registry.list_all()
            assert len(all_caps) == 5  # 1 tool + 2 skills + 1 instr + 1 plan

            types = {c.capability_type for c in all_caps}
            assert CapabilityType.TOOL in types
            assert CapabilityType.SKILL in types
            assert CapabilityType.INSTRUCTION in types
            assert CapabilityType.PLAN in types

            # Server tool should NOT be affected by file sync stale removal
            assert fresh_registry.get_by_name("add_numbers") is not None
