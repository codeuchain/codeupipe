"""
Tests for codeupipe.upgrade — Project scaffolding regeneration.

Verifies upgrade_project() detects existing CI, regenerates configs,
handles dry_run mode, and reports warnings for missing manifests.
"""

import pytest

from codeupipe.upgrade import upgrade_project


def _setup_project(root, ci_provider="github"):
    """Create a minimal codeupipe project with manifest and CI."""
    manifest = '[project]\nname = "upgrade-test"\n\n[deploy]\ntarget = "docker"\n'
    (root / "cup.toml").write_text(manifest)

    if ci_provider == "github":
        wf_dir = root / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("# old CI content that should change\n")


class TestUpgradeProject:
    """Test upgrade_project scaffolding regeneration."""

    @pytest.mark.unit
    def test_no_manifest(self, tmp_path):
        result = upgrade_project(str(tmp_path))
        assert len(result["warnings"]) > 0
        assert "cup.toml" in result["warnings"][0]
        assert result["updated"] == []

    @pytest.mark.unit
    def test_regenerates_ci(self, tmp_path):
        _setup_project(tmp_path)
        result = upgrade_project(str(tmp_path))
        # The old placeholder CI should now be regenerated
        assert len(result["updated"]) >= 1
        ci_path = tmp_path / ".github" / "workflows" / "ci.yml"
        content = ci_path.read_text()
        # Regenerated content should not be the old placeholder
        assert content != "# old CI content that should change\n"

    @pytest.mark.unit
    def test_dry_run_no_writes(self, tmp_path):
        _setup_project(tmp_path)
        old_ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
        result = upgrade_project(str(tmp_path), dry_run=True)
        # Should report updates but not actually write
        assert len(result["updated"]) >= 1
        new_ci = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
        assert new_ci == old_ci

    @pytest.mark.unit
    def test_no_ci_warns(self, tmp_path):
        (tmp_path / "cup.toml").write_text('[project]\nname = "bare"\n')
        result = upgrade_project(str(tmp_path))
        warning_texts = " ".join(result["warnings"])
        assert "ci" in warning_texts.lower() or "CI" in warning_texts

    @pytest.mark.unit
    def test_skip_when_unchanged(self, tmp_path):
        _setup_project(tmp_path)
        # First upgrade regenerates
        upgrade_project(str(tmp_path))
        # Second upgrade should skip (content already matches)
        result2 = upgrade_project(str(tmp_path))
        assert len(result2["skipped"]) >= 1
        assert len(result2["updated"]) == 0

    @pytest.mark.unit
    def test_result_structure(self, tmp_path):
        result = upgrade_project(str(tmp_path))
        assert "updated" in result
        assert "skipped" in result
        assert "warnings" in result
        assert isinstance(result["updated"], list)
        assert isinstance(result["skipped"], list)
        assert isinstance(result["warnings"], list)
