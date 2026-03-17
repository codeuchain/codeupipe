"""Integration tests for FileRegistrationChain.

Tests the full file-based registration pipeline:
  ScanSkills → ScanInstructions → ScanPlans → SyncLocal → Embed → Insert
"""

from unittest.mock import patch

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.pipelines.file_registration import build_file_registration_chain
from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder
from codeupipe.ai.discovery.registry import CapabilityRegistry


@pytest.fixture(autouse=True)
def _clean():
    SnowflakeArcticEmbedder.reset()
    yield
    SnowflakeArcticEmbedder.reset()


@pytest.fixture
def empty_registry(tmp_path):
    """Create a fresh empty registry."""
    db = tmp_path / "test.db"
    return CapabilityRegistry(db)


def _fake_embed_doc(text: str) -> np.ndarray:
    """Fake embedding for documents."""
    rng = np.random.default_rng(hash(text) % 2**32)
    vec = rng.random(1024).astype(np.float32)
    return vec / np.linalg.norm(vec)


@pytest.fixture
def populated_fs(tmp_path):
    """Create a filesystem with skills, instructions, and plans."""
    # Skills
    skills = tmp_path / "skills"
    skill_a = skills / "coding"
    skill_a.mkdir(parents=True)
    (skill_a / "SKILL.md").write_text(
        "---\nname: coding\ndescription: Code generation skill\n---\n\n# Coding\n"
    )

    # Instructions
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "style.instructions.md").write_text(
        "---\napplyTo: '**/*.py'\n---\n\n# Style Guide\n\nFollow PEP 8.\n"
    )

    # Plans
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ROADMAP.md").write_text("# Product Roadmap\n\n## Q1\n\nLaunch v1.\n")

    return tmp_path


@pytest.mark.integration
class TestFileRegistrationChain:
    """Integration tests for the file registration pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_registers_files(self, empty_registry, populated_fs):
        """Should register all scanned files in the registry."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_fake_embed_doc):

            chain = build_file_registration_chain()
            ctx = Payload({
                "skills_paths": [populated_fs / "skills"],
                "instructions_paths": [populated_fs / "prompts"],
                "plans_paths": [populated_fs / "docs"],
                "project_root": populated_fs,
                "capability_registry": empty_registry,
            })
            result = await chain.run(ctx)

            assert result.get("registered_count") == 3
            assert len(empty_registry.list_all()) == 3

    @pytest.mark.asyncio
    async def test_pipeline_stores_embeddings(self, empty_registry, populated_fs):
        """Registered capabilities should have embeddings."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_fake_embed_doc):

            chain = build_file_registration_chain()
            ctx = Payload({
                "skills_paths": [populated_fs / "skills"],
                "instructions_paths": [populated_fs / "prompts"],
                "plans_paths": [populated_fs / "docs"],
                "project_root": populated_fs,
                "capability_registry": empty_registry,
            })
            await chain.run(ctx)

            cap = empty_registry.get_by_name("coding")
            assert cap is not None
            assert cap.embedding is not None

    @pytest.mark.asyncio
    async def test_pipeline_sync_skips_unchanged(self, empty_registry, populated_fs):
        """Second run should skip unchanged files."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_fake_embed_doc):

            chain = build_file_registration_chain()
            ctx_data = {
                "skills_paths": [populated_fs / "skills"],
                "instructions_paths": [populated_fs / "prompts"],
                "plans_paths": [populated_fs / "docs"],
                "project_root": populated_fs,
                "capability_registry": empty_registry,
            }

            # First run
            result1 = await chain.run(Payload(ctx_data))
            assert result1.get("registered_count") == 3

            # Second run — sync should skip all
            result2 = await chain.run(Payload(ctx_data))
            stats = result2.get("sync_stats")
            assert stats["unchanged"] == 3
            assert stats["added"] == 0

    @pytest.mark.asyncio
    async def test_pipeline_detects_changes(self, empty_registry, populated_fs):
        """Should re-register files when content changes."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_fake_embed_doc):

            chain = build_file_registration_chain()
            ctx_data = {
                "skills_paths": [populated_fs / "skills"],
                "instructions_paths": [populated_fs / "prompts"],
                "plans_paths": [populated_fs / "docs"],
                "project_root": populated_fs,
                "capability_registry": empty_registry,
            }

            # First run
            await chain.run(Payload(ctx_data))

            # Modify a file
            skill_file = populated_fs / "skills" / "coding" / "SKILL.md"
            skill_file.write_text(
                "---\nname: coding\ndescription: Updated coding skill\n---\n\n# Coding v2\n"
            )

            # Second run — should detect the change
            result2 = await chain.run(Payload(ctx_data))
            stats = result2.get("sync_stats")
            assert stats["updated"] == 1
            assert stats["unchanged"] == 2

    @pytest.mark.asyncio
    async def test_pipeline_empty_dirs(self, empty_registry, tmp_path):
        """Should handle empty directories gracefully."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_fake_embed_doc):

            empty_skills = tmp_path / "skills"
            empty_skills.mkdir()
            empty_prompts = tmp_path / "prompts"
            empty_prompts.mkdir()
            empty_docs = tmp_path / "docs"
            empty_docs.mkdir()

            chain = build_file_registration_chain()
            ctx = Payload({
                "skills_paths": [empty_skills],
                "instructions_paths": [empty_prompts],
                "plans_paths": [empty_docs],
                "project_root": tmp_path,
                "capability_registry": empty_registry,
            })
            result = await chain.run(ctx)

            assert result.get("registered_count") == 0

    @pytest.mark.asyncio
    async def test_pipeline_removes_stale(self, empty_registry, populated_fs):
        """Should remove stale entries when files are deleted."""
        with patch.object(SnowflakeArcticEmbedder, "__init__", return_value=None), \
             patch.object(SnowflakeArcticEmbedder, "embed_document", side_effect=_fake_embed_doc):

            chain = build_file_registration_chain()
            ctx_data = {
                "skills_paths": [populated_fs / "skills"],
                "instructions_paths": [populated_fs / "prompts"],
                "plans_paths": [populated_fs / "docs"],
                "project_root": populated_fs,
                "capability_registry": empty_registry,
            }

            # First run registers 3
            await chain.run(Payload(ctx_data))
            assert len(empty_registry.list_all()) == 3

            # Delete the ROADMAP.md plan file
            (populated_fs / "docs" / "ROADMAP.md").unlink()

            # Second run should remove the stale entry
            result2 = await chain.run(Payload(ctx_data))
            stats = result2.get("sync_stats")
            assert stats["removed"] == 1

            # Registry should have 2 remaining
            assert len(empty_registry.list_all()) == 2
