"""Tests for ScanDirectory filter."""

import pytest

from codeupipe import Payload
from codeupipe.linter.scan_directory import ScanDirectory, classify_class, analyze_file


class TestScanDirectory:
    """Unit tests for ScanDirectory filter."""

    def test_scans_py_files(self, tmp_path):
        (tmp_path / "foo.py").write_text("class Foo:\n    def call(self, p): ...\n")
        (tmp_path / "bar.py").write_text("class Bar:\n    def observe(self, p): ...\n")
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        files = result.get("files")
        assert len(files) == 2
        stems = [f["stem"] for f in files]
        assert "foo" in stems
        assert "bar" in stems

    def test_skips_init_py(self, tmp_path):
        (tmp_path / "__init__.py").write_text("# init\n")
        (tmp_path / "real.py").write_text("x = 1\n")
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        assert len(result.get("files")) == 1
        assert result.get("files")[0]["stem"] == "real"

    def test_initializes_empty_issues(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        assert result.get("issues") == []

    def test_empty_directory(self, tmp_path):
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        assert result.get("files") == []
        assert result.get("issues") == []

    def test_directory_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ScanDirectory().call(Payload({"directory": str(tmp_path / "nope")}))

    def test_syntax_error_captured(self, tmp_path):
        (tmp_path / "bad.py").write_text("def broken(\n")
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        assert result.get("files")[0]["error"] is not None
        assert result.get("files")[0]["classes"] == []

    def test_detects_filter_class(self, tmp_path):
        (tmp_path / "f.py").write_text("class F:\n    def call(self, p): ...\n")
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        cls = result.get("files")[0]["classes"][0]
        assert cls[0] == "F"
        assert cls[1] == "filter"

    def test_detects_tap_class(self, tmp_path):
        (tmp_path / "t.py").write_text("class T:\n    def observe(self, p): ...\n")
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        assert result.get("files")[0]["classes"][0][1] == "tap"

    def test_detects_stream_filter(self, tmp_path):
        (tmp_path / "s.py").write_text("class S:\n    async def stream(self, c): yield c\n")
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        assert result.get("files")[0]["classes"][0][1] == "stream-filter"

    def test_detects_hook(self, tmp_path):
        code = "class H(Hook):\n    def before(self): ...\n    def after(self): ...\n    def on_error(self, e): ...\n"
        (tmp_path / "h.py").write_text(code)
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        assert result.get("files")[0]["classes"][0][1] == "hook"

    def test_detects_public_functions(self, tmp_path):
        (tmp_path / "helpers.py").write_text("def build_pipeline(): ...\ndef _private(): ...\n")
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        funcs = result.get("files")[0]["functions"]
        assert "build_pipeline" in funcs
        assert "_private" not in funcs

    def test_skips_private_classes(self, tmp_path):
        (tmp_path / "x.py").write_text("class _Internal:\n    def call(self, p): ...\n")
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        assert result.get("files")[0]["classes"] == []

    def test_files_sorted_alphabetically(self, tmp_path):
        (tmp_path / "z.py").write_text("x = 1\n")
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "m.py").write_text("x = 1\n")
        result = ScanDirectory().call(Payload({"directory": str(tmp_path)}))
        stems = [f["stem"] for f in result.get("files")]
        assert stems == ["a", "m", "z"]


class TestClassifyClass:
    """Unit tests for classify_class helper."""

    def test_filter_by_call(self):
        import ast
        tree = ast.parse("class F:\n    def call(self): ...\n")
        node = tree.body[0]
        assert classify_class(node) == "filter"

    def test_tap_by_observe(self):
        import ast
        tree = ast.parse("class T:\n    def observe(self): ...\n")
        assert classify_class(tree.body[0]) == "tap"

    def test_stream_filter_by_stream(self):
        import ast
        tree = ast.parse("class S:\n    async def stream(self): ...\n")
        assert classify_class(tree.body[0]) == "stream-filter"

    def test_hook_by_base_class(self):
        import ast
        tree = ast.parse("class H(Hook):\n    pass\n")
        assert classify_class(tree.body[0]) == "hook"

    def test_unknown_returns_none(self):
        import ast
        tree = ast.parse("class X:\n    def something(self): ...\n")
        assert classify_class(tree.body[0]) is None


class TestAnalyzeFile:
    """Unit tests for analyze_file helper."""

    def test_returns_path_and_stem(self, tmp_path):
        f = tmp_path / "my_filter.py"
        f.write_text("x = 1\n")
        info = analyze_file(f)
        assert info["path"] == str(f)
        assert info["stem"] == "my_filter"
        assert info["error"] is None

    def test_os_error(self, tmp_path):
        info = analyze_file(tmp_path / "nonexistent.py")
        assert info["error"] is not None
