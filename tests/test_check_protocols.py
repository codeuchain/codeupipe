"""Tests for CheckProtocols filter."""

import pytest

from codeupipe import Payload
from codeupipe.linter.check_protocols import CheckProtocols


def _file(path, classes, error=None):
    return {"path": path, "stem": "x", "classes": classes, "functions": [], "error": error}


class TestCheckProtocols:
    """Unit tests for CheckProtocols filter."""

    # ── CUP000: Syntax error ──

    def test_syntax_error_flagged(self):
        files = [_file("/bad.py", [], error="invalid syntax")]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        issues = result.get("issues")
        assert len(issues) == 1
        assert issues[0][0] == "CUP000"
        assert issues[0][1] == "error"
        assert "Syntax error" in issues[0][3]

    # ── CUP003: Filter missing call() ──

    def test_filter_with_call_passes(self):
        files = [_file("/f.py", [("F", "filter", {"call", "__init__"})])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        assert result.get("issues") == []

    def test_filter_missing_call_flagged(self):
        files = [_file("/f.py", [("F", "filter", {"__init__"})])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        issues = result.get("issues")
        assert len(issues) == 1
        assert issues[0][0] == "CUP003"
        assert "call()" in issues[0][3]

    # ── CUP004: Tap missing observe() ──

    def test_tap_with_observe_passes(self):
        files = [_file("/t.py", [("T", "tap", {"observe"})])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        assert result.get("issues") == []

    def test_tap_missing_observe_flagged(self):
        files = [_file("/t.py", [("T", "tap", {"__init__"})])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        issues = result.get("issues")
        assert len(issues) == 1
        assert issues[0][0] == "CUP004"
        assert "observe()" in issues[0][3]

    # ── CUP005: StreamFilter missing stream() ──

    def test_stream_filter_with_stream_passes(self):
        files = [_file("/s.py", [("S", "stream-filter", {"stream"})])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        assert result.get("issues") == []

    def test_stream_filter_missing_stream_flagged(self):
        files = [_file("/s.py", [("S", "stream-filter", {"call"})])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        issues = result.get("issues")
        assert len(issues) == 1
        assert issues[0][0] == "CUP005"
        assert "stream()" in issues[0][3]

    # ── CUP006: Hook missing lifecycle methods ──

    def test_hook_complete_passes(self):
        files = [_file("/h.py", [("H", "hook", {"before", "after", "on_error"})])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        assert result.get("issues") == []

    def test_hook_missing_one_method_flagged(self):
        files = [_file("/h.py", [("H", "hook", {"before", "after"})])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        issues = result.get("issues")
        assert len(issues) == 1
        assert issues[0][0] == "CUP006"
        assert "on_error" in issues[0][3]

    def test_hook_missing_all_methods_flagged(self):
        files = [_file("/h.py", [("H", "hook", set())])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        issues = result.get("issues")
        assert len(issues) == 1
        assert issues[0][0] == "CUP006"
        assert "after" in issues[0][3]
        assert "before" in issues[0][3]
        assert "on_error" in issues[0][3]

    # ── Edge cases ──

    def test_non_component_classes_skipped(self):
        files = [_file("/u.py", [("Util", None, {"helper"})])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        assert result.get("issues") == []

    def test_multiple_violations_in_one_file(self):
        files = [_file("/multi.py", [
            ("F", "filter", set()),
            ("T", "tap", set()),
        ])]
        result = CheckProtocols().call(Payload({"files": files, "issues": []}))
        issues = result.get("issues")
        rules = [i[0] for i in issues]
        assert "CUP003" in rules
        assert "CUP004" in rules

    def test_preserves_existing_issues(self):
        files = [_file("/f.py", [("F", "filter", set())])]
        payload = Payload({"files": files, "issues": [("OLD", "warn", "/", "pre")]})
        result = CheckProtocols().call(payload)
        assert result.get("issues")[0][0] == "OLD"

    def test_empty_files_no_issues(self):
        result = CheckProtocols().call(Payload({"files": [], "issues": []}))
        assert result.get("issues") == []
