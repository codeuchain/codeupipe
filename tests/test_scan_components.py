"""Tests for ScanComponents filter."""

import pytest

from codeupipe import Payload
from codeupipe.linter.scan_components import ScanComponents


class TestScanComponents:
    """Unit tests for ScanComponents filter."""

    def test_finds_filter_class(self, tmp_path):
        (tmp_path / "auth.py").write_text(
            "class Auth:\n"
            "    def call(self, p): return p\n"
            "    def validate(self, x): ...\n"
        )
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        comps = result.get("components")
        assert len(comps) == 1
        assert comps[0]["name"] == "Auth"
        assert comps[0]["kind"] == "filter"
        assert "call" in comps[0]["methods"]
        assert "validate" in comps[0]["methods"]

    def test_finds_tap_class(self, tmp_path):
        (tmp_path / "audit.py").write_text(
            "class Audit:\n    def observe(self, p): pass\n"
        )
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        assert result.get("components")[0]["kind"] == "tap"

    def test_finds_hook_class(self, tmp_path):
        (tmp_path / "logger.py").write_text(
            "class Logger(Hook):\n"
            "    def before(self, p): ...\n"
            "    def after(self, p): ...\n"
            "    def on_error(self, p, e): ...\n"
        )
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        assert result.get("components")[0]["kind"] == "hook"

    def test_finds_stream_filter(self, tmp_path):
        (tmp_path / "parser.py").write_text(
            "class Parser:\n    async def stream(self, chunk): yield chunk\n"
        )
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        assert result.get("components")[0]["kind"] == "stream-filter"

    def test_finds_builder_function(self, tmp_path):
        (tmp_path / "pipeline.py").write_text(
            "def build_auth_pipeline(): ...\n"
        )
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        comps = result.get("components")
        assert len(comps) == 1
        assert comps[0]["name"] == "build_auth_pipeline"
        assert comps[0]["kind"] == "builder"

    def test_skips_private_classes(self, tmp_path):
        (tmp_path / "internal.py").write_text(
            "class _Internal:\n    def call(self, p): ...\n"
        )
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        assert result.get("components") == []

    def test_skips_non_component_classes(self, tmp_path):
        (tmp_path / "util.py").write_text(
            "class Helper:\n    def do_stuff(self): ...\n"
        )
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        assert result.get("components") == []

    def test_skips_init_py(self, tmp_path):
        (tmp_path / "__init__.py").write_text("from .auth import Auth\n")
        (tmp_path / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        assert len(result.get("components")) == 1

    def test_skips_syntax_errors(self, tmp_path):
        (tmp_path / "bad.py").write_text("def broken(\n")
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        assert result.get("components") == []

    def test_excludes_private_methods(self, tmp_path):
        (tmp_path / "f.py").write_text(
            "class F:\n"
            "    def call(self, p): ...\n"
            "    def _helper(self): ...\n"
            "    def __init__(self): ...\n"
        )
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        methods = result.get("components")[0]["methods"]
        assert "call" in methods
        assert "_helper" not in methods
        assert "__init__" not in methods

    def test_multiple_files(self, tmp_path):
        (tmp_path / "a.py").write_text("class A:\n    def call(self, p): ...\n")
        (tmp_path / "b.py").write_text("class B:\n    def observe(self, p): ...\n")
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        names = [c["name"] for c in result.get("components")]
        assert "A" in names
        assert "B" in names

    def test_directory_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ScanComponents().call(Payload({"directory": str(tmp_path / "nope")}))

    def test_empty_directory(self, tmp_path):
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        assert result.get("components") == []

    def test_records_file_and_stem(self, tmp_path):
        (tmp_path / "validate_email.py").write_text(
            "class ValidateEmail:\n    def call(self, p): ...\n"
        )
        result = ScanComponents().call(Payload({"directory": str(tmp_path)}))
        comp = result.get("components")[0]
        assert comp["stem"] == "validate_email"
        assert "validate_email.py" in comp["file"]
