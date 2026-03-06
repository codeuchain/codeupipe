"""Tests for CheckIndex filter — verifies INDEX.md structural coverage."""

import pytest
from pathlib import Path

from codeupipe import Payload
from codeupipe.testing import run_filter
from codeupipe.linter import CheckIndex


class TestCheckIndex:
    """Unit tests for the CheckIndex filter."""

    def test_no_issues_when_all_key_files_referenced(self, tmp_path):
        """When all key files are in doc_refs, index_issues is empty."""
        # Create a minimal codeupipe package structure
        pkg = tmp_path / "codeupipe"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("# root")
        core = pkg / "core"
        core.mkdir()
        (core / "__init__.py").write_text("# core")
        (core / "payload.py").write_text("class Payload: pass")

        doc_refs = [
            {"file": "codeupipe/__init__.py", "symbols": [], "hash": None},
            {"file": "codeupipe/core/__init__.py", "symbols": [], "hash": None},
            {"file": "codeupipe/core/payload.py", "symbols": [], "hash": None},
        ]

        result = run_filter(CheckIndex(), {
            "directory": str(tmp_path),
            "doc_refs": doc_refs,
        })

        issues = result.get("index_issues")
        assert issues == []

    def test_detects_unmapped_key_files(self, tmp_path):
        """When a key file is not in doc_refs, it's reported."""
        pkg = tmp_path / "codeupipe"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("# root")
        (pkg / "cli.py").write_text("def main(): pass")

        # Only reference __init__.py, not cli.py
        doc_refs = [
            {"file": "codeupipe/__init__.py", "symbols": [], "hash": None},
        ]

        result = run_filter(CheckIndex(), {
            "directory": str(tmp_path),
            "doc_refs": doc_refs,
        })

        issues = result.get("index_issues")
        assert len(issues) == 1
        assert issues[0]["file"] == "codeupipe/cli.py"

    def test_ignores_pycache(self, tmp_path):
        """Files in __pycache__ are not flagged."""
        pkg = tmp_path / "codeupipe"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("# root")
        cache = pkg / "__pycache__"
        cache.mkdir()
        (cache / "foo.cpython-39.pyc").write_text("")

        result = run_filter(CheckIndex(), {
            "directory": str(tmp_path),
            "doc_refs": [
                {"file": "codeupipe/__init__.py", "symbols": [], "hash": None},
            ],
        })

        assert result.get("index_issues") == []

    def test_ignores_individual_linter_filters(self, tmp_path):
        """Individual filter files inside linter/ are not required in index."""
        pkg = tmp_path / "codeupipe"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("# root")
        linter = pkg / "linter"
        linter.mkdir()
        (linter / "__init__.py").write_text("# linter")
        (linter / "lint_pipeline.py").write_text("def build(): pass")
        (linter / "check_naming.py").write_text("class CheckNaming: pass")
        (linter / "scan_directory.py").write_text("class ScanDirectory: pass")

        result = run_filter(CheckIndex(), {
            "directory": str(tmp_path),
            "doc_refs": [
                {"file": "codeupipe/__init__.py", "symbols": [], "hash": None},
                {"file": "codeupipe/linter/__init__.py", "symbols": [], "hash": None},
                {"file": "codeupipe/linter/lint_pipeline.py", "symbols": [], "hash": None},
            ],
        })

        # check_naming.py and scan_directory.py should be ignored (individual filters)
        assert result.get("index_issues") == []

    def test_empty_directory_no_crash(self, tmp_path):
        """When codeupipe/ doesn't exist, returns empty issues."""
        result = run_filter(CheckIndex(), {
            "directory": str(tmp_path),
            "doc_refs": [],
        })
        assert result.get("index_issues") == []

    def test_ignores_individual_converter_files(self, tmp_path):
        """Individual non-pipeline files inside converter/ are not required."""
        pkg = tmp_path / "codeupipe"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("# root")
        conv = pkg / "converter"
        conv.mkdir()
        (conv / "__init__.py").write_text("# conv")
        (conv / "config.py").write_text("CONFIG = {}")
        (conv / "helpers.py").write_text("def help(): pass")

        result = run_filter(CheckIndex(), {
            "directory": str(tmp_path),
            "doc_refs": [
                {"file": "codeupipe/__init__.py", "symbols": [], "hash": None},
                {"file": "codeupipe/converter/__init__.py", "symbols": [], "hash": None},
            ],
        })

        # config.py and helpers.py should be ignored (individual converter files)
        assert result.get("index_issues") == []

    def test_pipeline_files_in_linter_are_tracked(self, tmp_path):
        """Pipeline builder files (*_pipeline.py) in linter/ ARE tracked."""
        pkg = tmp_path / "codeupipe"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("# root")
        linter = pkg / "linter"
        linter.mkdir()
        (linter / "__init__.py").write_text("# linter")
        (linter / "lint_pipeline.py").write_text("def build(): pass")
        (linter / "doc_check_pipeline.py").write_text("def build(): pass")

        # Missing doc_check_pipeline.py reference
        result = run_filter(CheckIndex(), {
            "directory": str(tmp_path),
            "doc_refs": [
                {"file": "codeupipe/__init__.py", "symbols": [], "hash": None},
                {"file": "codeupipe/linter/__init__.py", "symbols": [], "hash": None},
                {"file": "codeupipe/linter/lint_pipeline.py", "symbols": [], "hash": None},
            ],
        })

        issues = result.get("index_issues")
        assert len(issues) == 1
        assert "doc_check_pipeline.py" in issues[0]["file"]
