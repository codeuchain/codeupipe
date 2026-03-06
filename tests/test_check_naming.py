"""Tests for CheckNaming filter."""

import pytest

from codeupipe import Payload
from codeupipe.linter.check_naming import CheckNaming


def _make_payload(stems):
    """Build a payload with file stubs for the given stems."""
    files = [{"path": f"/fake/{s}.py", "stem": s, "classes": [], "functions": [], "error": None} for s in stems]
    return Payload({"files": files, "issues": []})


class TestCheckNaming:
    """Unit tests for CheckNaming filter."""

    def test_snake_case_passes(self):
        result = CheckNaming().call(_make_payload(["validate_email", "hash_password"]))
        assert result.get("issues") == []

    def test_pascal_case_flagged(self):
        result = CheckNaming().call(_make_payload(["ValidateEmail"]))
        issues = result.get("issues")
        assert len(issues) == 1
        assert issues[0][0] == "CUP007"
        assert "snake_case" in issues[0][3]
        assert "validate_email" in issues[0][3]

    def test_mixed_case_flagged(self):
        result = CheckNaming().call(_make_payload(["myFilter"]))
        issues = result.get("issues")
        assert len(issues) == 1
        assert issues[0][0] == "CUP007"

    def test_single_word_passes(self):
        result = CheckNaming().call(_make_payload(["scan"]))
        assert result.get("issues") == []

    def test_numbers_in_name_pass(self):
        result = CheckNaming().call(_make_payload(["step2_validate"]))
        assert result.get("issues") == []

    def test_preserves_existing_issues(self):
        payload = Payload({
            "files": [{"path": "/fake/Bad.py", "stem": "Bad", "classes": [], "functions": [], "error": None}],
            "issues": [("EXISTING", "error", "/fake", "old issue")],
        })
        result = CheckNaming().call(payload)
        issues = result.get("issues")
        assert len(issues) == 2
        assert issues[0][0] == "EXISTING"
        assert issues[1][0] == "CUP007"

    def test_empty_files_no_issues(self):
        result = CheckNaming().call(Payload({"files": [], "issues": []}))
        assert result.get("issues") == []

    def test_severity_is_warning(self):
        result = CheckNaming().call(_make_payload(["BadName"]))
        assert result.get("issues")[0][1] == "warning"
