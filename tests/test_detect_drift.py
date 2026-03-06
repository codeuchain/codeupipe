"""Tests for DetectDrift filter — compare stored hashes with current file hashes."""

from pathlib import Path

from codeupipe import Payload
from codeupipe.testing import run_filter


class TestDetectDrift:
    """DetectDrift: flag refs where stored hash differs from current hash."""

    def test_no_drift_when_hash_matches(self, tmp_path):
        from codeupipe.linter.detect_drift import DetectDrift

        refs = [{
            "file": "state.py", "symbols": [], "hash": "abc1234",
            "exists": True, "current_hash": "abc1234",
            "doc_path": "DOC.md", "line": 5, "abs_path": str(tmp_path / "state.py"),
        }]
        result = run_filter(DetectDrift(), {"resolved_refs": refs})
        drifted = result.get("drifted_refs")
        assert drifted == []

    def test_detects_hash_mismatch(self, tmp_path):
        from codeupipe.linter.detect_drift import DetectDrift

        refs = [{
            "file": "state.py", "symbols": [], "hash": "old1234",
            "exists": True, "current_hash": "new5678",
            "doc_path": "DOC.md", "line": 5, "abs_path": str(tmp_path / "state.py"),
        }]
        result = run_filter(DetectDrift(), {"resolved_refs": refs})
        drifted = result.get("drifted_refs")
        assert len(drifted) == 1
        assert drifted[0]["file"] == "state.py"
        assert drifted[0]["stored_hash"] == "old1234"
        assert drifted[0]["current_hash"] == "new5678"

    def test_skips_refs_without_stored_hash(self, tmp_path):
        from codeupipe.linter.detect_drift import DetectDrift

        refs = [{
            "file": "state.py", "symbols": ["State"], "hash": None,
            "exists": True, "current_hash": "abc1234",
            "doc_path": "DOC.md", "line": 5, "abs_path": str(tmp_path / "state.py"),
        }]
        result = run_filter(DetectDrift(), {"resolved_refs": refs})
        # No stored hash → no drift check (symbol-only mode)
        assert result.get("drifted_refs") == []

    def test_flags_missing_file_as_drift(self, tmp_path):
        from codeupipe.linter.detect_drift import DetectDrift

        refs = [{
            "file": "gone.py", "symbols": [], "hash": "old1234",
            "exists": False, "current_hash": None,
            "doc_path": "DOC.md", "line": 1, "abs_path": str(tmp_path / "gone.py"),
        }]
        result = run_filter(DetectDrift(), {"resolved_refs": refs})
        drifted = result.get("drifted_refs")
        assert len(drifted) == 1
        assert drifted[0]["file"] == "gone.py"

    def test_multiple_refs_mixed(self, tmp_path):
        from codeupipe.linter.detect_drift import DetectDrift

        refs = [
            {"file": "a.py", "symbols": [], "hash": "aaa",
             "exists": True, "current_hash": "aaa",
             "doc_path": "DOC.md", "line": 1, "abs_path": ""},
            {"file": "b.py", "symbols": [], "hash": "bbb",
             "exists": True, "current_hash": "ccc",
             "doc_path": "DOC.md", "line": 10, "abs_path": ""},
        ]
        result = run_filter(DetectDrift(), {"resolved_refs": refs})
        drifted = result.get("drifted_refs")
        assert len(drifted) == 1
        assert drifted[0]["file"] == "b.py"
