"""Tests for ResolveRefs filter — verify source files exist and compute hashes."""

from pathlib import Path
import hashlib

from codeupipe import Payload
from codeupipe.testing import run_filter


def _file_hash(path: Path) -> str:
    """Compute the same short hash the filter should use."""
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:7]


class TestResolveRefs:
    """ResolveRefs: resolve file paths and compute current content hashes."""

    def test_resolves_existing_file(self, tmp_path):
        src = tmp_path / "state.py"
        src.write_text("class State:\n    pass\n")
        from codeupipe.linter.resolve_refs import ResolveRefs

        refs = [{"file": "state.py", "symbols": [], "hash": None,
                 "doc_path": "README.md", "line": 5}]
        result = run_filter(ResolveRefs(), {
            "directory": str(tmp_path),
            "doc_refs": refs,
        })
        resolved = result.get("resolved_refs")
        assert len(resolved) == 1
        assert resolved[0]["exists"] is True
        assert resolved[0]["current_hash"] == _file_hash(src)

    def test_marks_missing_file(self, tmp_path):
        from codeupipe.linter.resolve_refs import ResolveRefs

        refs = [{"file": "missing.py", "symbols": [], "hash": None,
                 "doc_path": "DOC.md", "line": 1}]
        result = run_filter(ResolveRefs(), {
            "directory": str(tmp_path),
            "doc_refs": refs,
        })
        resolved = result.get("resolved_refs")
        assert resolved[0]["exists"] is False
        assert resolved[0]["current_hash"] is None

    def test_preserves_original_ref_data(self, tmp_path):
        src = tmp_path / "core.py"
        src.write_text("x = 1\n")
        from codeupipe.linter.resolve_refs import ResolveRefs

        refs = [{"file": "core.py", "symbols": ["Foo"], "hash": "abc1234",
                 "doc_path": "DOC.md", "line": 10}]
        result = run_filter(ResolveRefs(), {
            "directory": str(tmp_path),
            "doc_refs": refs,
        })
        resolved = result.get("resolved_refs")
        assert resolved[0]["symbols"] == ["Foo"]
        assert resolved[0]["hash"] == "abc1234"
        assert resolved[0]["doc_path"] == "DOC.md"
        assert resolved[0]["line"] == 10
