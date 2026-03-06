"""Tests for ScanTests filter."""

import pytest

from codeupipe import Payload
from codeupipe.linter.scan_tests import ScanTests, _extract_imports, _extract_test_methods


def _comp(stem, name="Comp", kind="filter"):
    return {"file": f"/fake/{stem}.py", "stem": stem, "name": name, "kind": kind, "methods": ["call"]}


class TestScanTests:
    """Unit tests for ScanTests filter."""

    def test_finds_matching_test_file(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_auth.py").write_text(
            "from myapp.auth import Auth\n\n"
            "class TestAuth:\n"
            "    def test_happy(self): ...\n"
            "    def test_sad(self): ...\n"
        )
        payload = Payload({"components": [_comp("auth", "Auth")], "tests_dir": str(tests_dir)})
        result = ScanTests().call(payload)
        tm = result.get("test_map")
        assert len(tm) == 1
        assert tm[0]["stem"] == "auth"
        assert len(tm[0]["test_methods"]) == 2
        assert "Auth" in tm[0]["imports"]

    def test_ignores_unrelated_test_files(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_unrelated.py").write_text("def test_x(): ...\n")
        payload = Payload({"components": [_comp("auth")], "tests_dir": str(tests_dir)})
        result = ScanTests().call(payload)
        assert result.get("test_map") == []

    def test_extracts_referenced_methods(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_auth.py").write_text(
            "from myapp import Auth\n\n"
            "class TestAuth:\n"
            "    def test_call(self):\n"
            "        Auth().call(payload)\n"
        )
        payload = Payload({"components": [_comp("auth")], "tests_dir": str(tests_dir)})
        result = ScanTests().call(payload)
        assert "call" in result.get("test_map")[0]["referenced_methods"]

    def test_no_tests_dir(self, tmp_path):
        payload = Payload({"components": [_comp("auth")], "tests_dir": str(tmp_path / "nope")})
        result = ScanTests().call(payload)
        assert result.get("test_map") == []

    def test_empty_components(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_auth.py").write_text("def test_x(): ...\n")
        payload = Payload({"components": [], "tests_dir": str(tests_dir)})
        result = ScanTests().call(payload)
        assert result.get("test_map") == []

    def test_top_level_test_functions(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_auth.py").write_text(
            "from myapp import Auth\n\n"
            "def test_standalone(): ...\n"
        )
        payload = Payload({"components": [_comp("auth")], "tests_dir": str(tests_dir)})
        result = ScanTests().call(payload)
        assert "test_standalone" in result.get("test_map")[0]["test_methods"]

    def test_syntax_error_in_test_skipped(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_auth.py").write_text("def broken(\n")
        payload = Payload({"components": [_comp("auth")], "tests_dir": str(tests_dir)})
        result = ScanTests().call(payload)
        assert result.get("test_map") == []


class TestExtractImports:
    def test_from_import(self):
        import ast
        tree = ast.parse("from myapp.auth import Auth, helper\n")
        names = _extract_imports(tree)
        assert "Auth" in names
        assert "helper" in names

    def test_regular_import(self):
        import ast
        tree = ast.parse("import myapp.auth\n")
        names = _extract_imports(tree)
        assert "auth" in names


class TestExtractTestMethods:
    def test_class_methods(self):
        import ast
        tree = ast.parse(
            "class TestFoo:\n"
            "    def test_a(self): ...\n"
            "    def test_b(self): ...\n"
            "    def helper(self): ...\n"
        )
        methods = _extract_test_methods(tree)
        assert methods == ["test_a", "test_b"]

    def test_top_level_functions(self):
        import ast
        tree = ast.parse("def test_standalone(): ...\ndef helper(): ...\n")
        methods = _extract_test_methods(tree)
        assert methods == ["test_standalone"]
