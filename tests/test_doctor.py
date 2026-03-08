"""
Tests for codeupipe.doctor — Project health diagnostics.

Tests each check in isolation via tmp_path projects and verifies
the summary aggregation.
"""

import json

import pytest

from codeupipe.doctor import diagnose


def _write_manifest(root, extra=""):
    """Helper: write a minimal valid cup.toml."""
    (root / "cup.toml").write_text(
        f'[project]\nname = "test-project"\n{extra}'
    )


class TestDiagnoseManifest:
    """diagnose — manifest check."""

    @pytest.mark.unit
    def test_missing_manifest(self, tmp_path):
        result = diagnose(str(tmp_path))
        assert result["manifest"]["ok"] is False
        assert "No cup.toml" in result["manifest"]["message"]

    @pytest.mark.unit
    def test_valid_manifest(self, tmp_path):
        _write_manifest(tmp_path)
        result = diagnose(str(tmp_path))
        assert result["manifest"]["ok"] is True
        assert "test-project" in result["manifest"]["message"]

    @pytest.mark.unit
    def test_invalid_manifest(self, tmp_path):
        (tmp_path / "cup.toml").write_text("not valid toml [[[")
        result = diagnose(str(tmp_path))
        assert result["manifest"]["ok"] is False


class TestDiagnoseCi:
    """diagnose — CI config check."""

    @pytest.mark.unit
    def test_no_ci(self, tmp_path):
        _write_manifest(tmp_path)
        result = diagnose(str(tmp_path))
        assert result["ci"]["ok"] is False
        assert "No CI" in result["ci"]["message"]

    @pytest.mark.unit
    def test_with_github_actions(self, tmp_path):
        _write_manifest(tmp_path)
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n")
        result = diagnose(str(tmp_path))
        assert result["ci"]["ok"] is True


class TestDiagnoseTests:
    """diagnose — tests directory check."""

    @pytest.mark.unit
    def test_no_tests_dir(self, tmp_path):
        _write_manifest(tmp_path)
        result = diagnose(str(tmp_path))
        assert result["tests"]["ok"] is False

    @pytest.mark.unit
    def test_empty_tests_dir(self, tmp_path):
        _write_manifest(tmp_path)
        (tmp_path / "tests").mkdir()
        result = diagnose(str(tmp_path))
        assert result["tests"]["ok"] is False

    @pytest.mark.unit
    def test_with_test_files(self, tmp_path):
        _write_manifest(tmp_path)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_example.py").write_text("def test_ok(): pass\n")
        result = diagnose(str(tmp_path))
        assert result["tests"]["ok"] is True


class TestDiagnoseConnectors:
    """diagnose — connector health check."""

    @pytest.mark.unit
    def test_no_connectors(self, tmp_path):
        _write_manifest(tmp_path)
        result = diagnose(str(tmp_path))
        assert result["connectors"]["ok"] is True
        assert "No connectors" in result["connectors"]["message"]

    @pytest.mark.unit
    def test_with_connectors(self, tmp_path):
        _write_manifest(
            tmp_path,
            '[connectors.stripe]\nprovider = "stripe"\napi_key_env = "STRIPE_KEY"\n',
        )
        result = diagnose(str(tmp_path))
        assert result["connectors"]["ok"] is True
        assert "1 connector" in result["connectors"]["message"]


class TestDiagnoseSummary:
    """diagnose — summary aggregation."""

    @pytest.mark.unit
    def test_summary_present(self, tmp_path):
        result = diagnose(str(tmp_path))
        s = result["_summary"]
        assert "total" in s
        assert "passing" in s
        assert "failing" in s
        assert "healthy" in s
        assert s["total"] == 6

    @pytest.mark.unit
    def test_healthy_project(self, tmp_path):
        """A project with manifest and tests passes at least those checks."""
        _write_manifest(tmp_path)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_basic.py").write_text("def test_ok(): pass\n")
        # Add CI
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n")
        result = diagnose(str(tmp_path))
        s = result["_summary"]
        # manifest, ci, tests, connectors should pass
        assert s["passing"] >= 4
