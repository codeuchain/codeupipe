"""Tests for CheckStructure filter."""

import pytest

from codeupipe import Payload
from codeupipe.linter.check_structure import CheckStructure


def _file(path, classes, error=None):
    return {"path": path, "stem": "x", "classes": classes, "functions": [], "error": error}


class TestCheckStructure:
    """Unit tests for CheckStructure filter."""

    def test_single_component_passes(self):
        files = [_file("/f.py", [("Foo", "filter", {"call"})])]
        result = CheckStructure().call(Payload({"files": files, "issues": []}))
        assert result.get("issues") == []

    def test_multiple_components_flagged(self):
        files = [_file("/f.py", [
            ("Foo", "filter", {"call"}),
            ("Bar", "tap", {"observe"}),
        ])]
        result = CheckStructure().call(Payload({"files": files, "issues": []}))
        issues = result.get("issues")
        assert len(issues) == 1
        assert issues[0][0] == "CUP001"
        assert issues[0][1] == "error"
        assert "Foo (filter)" in issues[0][3]
        assert "Bar (tap)" in issues[0][3]

    def test_non_component_classes_ignored(self):
        files = [_file("/f.py", [
            ("Foo", "filter", {"call"}),
            ("Helper", None, {"do_stuff"}),
        ])]
        result = CheckStructure().call(Payload({"files": files, "issues": []}))
        assert result.get("issues") == []

    def test_skips_files_with_errors(self):
        files = [_file("/f.py", [], error="syntax error")]
        result = CheckStructure().call(Payload({"files": files, "issues": []}))
        assert result.get("issues") == []

    def test_preserves_existing_issues(self):
        files = [_file("/f.py", [("A", "filter", {"call"}), ("B", "tap", {"observe"})])]
        payload = Payload({"files": files, "issues": [("OLD", "warning", "/x", "old")]})
        result = CheckStructure().call(payload)
        assert len(result.get("issues")) == 2
        assert result.get("issues")[0][0] == "OLD"

    def test_empty_files_no_issues(self):
        result = CheckStructure().call(Payload({"files": [], "issues": []}))
        assert result.get("issues") == []

    def test_no_component_classes_passes(self):
        files = [_file("/f.py", [("Util", None, {"helper"})])]
        result = CheckStructure().call(Payload({"files": files, "issues": []}))
        assert result.get("issues") == []

    def test_three_components_flagged(self):
        files = [_file("/f.py", [
            ("A", "filter", {"call"}),
            ("B", "tap", {"observe"}),
            ("C", "filter", {"call"}),
        ])]
        result = CheckStructure().call(Payload({"files": files, "issues": []}))
        issues = result.get("issues")
        assert len(issues) == 1
        assert "A (filter)" in issues[0][3]
        assert "B (tap)" in issues[0][3]
        assert "C (filter)" in issues[0][3]
