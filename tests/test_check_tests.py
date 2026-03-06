"""Tests for CheckTests filter."""

import pytest

from codeupipe import Payload
from codeupipe.linter.check_tests import CheckTests


def _file(stem, classes=None, functions=None, error=None):
    return {
        "path": f"/fake/{stem}.py",
        "stem": stem,
        "classes": classes or [],
        "functions": functions or [],
        "error": error,
    }


class TestCheckTests:
    """Unit tests for CheckTests filter."""

    def test_existing_test_file_passes(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_my_filter.py").write_text("# test\n")
        files = [_file("my_filter", classes=[("MyFilter", "filter", {"call"})])]
        payload = Payload({"files": files, "issues": [], "tests_dir": str(tests_dir)})
        result = CheckTests().call(payload)
        assert result.get("issues") == []

    def test_missing_test_file_flagged(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        files = [_file("my_filter", classes=[("MyFilter", "filter", {"call"})])]
        payload = Payload({"files": files, "issues": [], "tests_dir": str(tests_dir)})
        result = CheckTests().call(payload)
        issues = result.get("issues")
        assert len(issues) == 1
        assert issues[0][0] == "CUP002"
        assert issues[0][1] == "warning"
        assert "test_my_filter" in issues[0][3]

    def test_builder_function_needs_test(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        files = [_file("pipeline", functions=["build_pipeline"])]
        payload = Payload({"files": files, "issues": [], "tests_dir": str(tests_dir)})
        result = CheckTests().call(payload)
        assert len(result.get("issues")) == 1
        assert result.get("issues")[0][0] == "CUP002"

    def test_non_component_file_skipped(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        files = [_file("helpers", classes=[("Util", None, {"do_stuff"})])]
        payload = Payload({"files": files, "issues": [], "tests_dir": str(tests_dir)})
        result = CheckTests().call(payload)
        assert result.get("issues") == []

    def test_skips_files_with_errors(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        files = [_file("broken", error="syntax error")]
        payload = Payload({"files": files, "issues": [], "tests_dir": str(tests_dir)})
        result = CheckTests().call(payload)
        assert result.get("issues") == []

    def test_preserves_existing_issues(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        files = [_file("x", classes=[("X", "filter", {"call"})])]
        payload = Payload({
            "files": files,
            "issues": [("OLD", "warn", "/", "old")],
            "tests_dir": str(tests_dir),
        })
        result = CheckTests().call(payload)
        assert result.get("issues")[0][0] == "OLD"

    def test_empty_files(self):
        result = CheckTests().call(Payload({"files": [], "issues": []}))
        assert result.get("issues") == []

    def test_default_tests_dir(self):
        """Default tests_dir is 'tests' when not specified."""
        files = [_file("x", classes=[("X", "filter", {"call"})])]
        result = CheckTests().call(Payload({"files": files, "issues": []}))
        issues = result.get("issues")
        assert len(issues) == 1
        assert "tests/test_x.py" in issues[0][3]
