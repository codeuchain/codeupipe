"""Tests for CheckSymbols filter — verify referenced symbols exist in source files."""

from pathlib import Path

from codeupipe import Payload
from codeupipe.testing import run_filter


class TestCheckSymbols:
    """CheckSymbols: AST-verify that referenced symbols exist in their source files."""

    def test_finds_existing_class(self, tmp_path):
        src = tmp_path / "state.py"
        src.write_text("class State:\n    executed = []\n    skipped = []\n")
        from codeupipe.linter.check_symbols import CheckSymbols

        refs = [{
            "file": "state.py", "symbols": ["State"],
            "hash": None, "exists": True, "current_hash": "abc",
            "doc_path": "DOC.md", "line": 1, "abs_path": str(src),
        }]
        result = run_filter(CheckSymbols(), {
            "directory": str(tmp_path),
            "resolved_refs": refs,
        })
        issues = result.get("symbol_issues")
        assert issues == []

    def test_detects_missing_symbol(self, tmp_path):
        src = tmp_path / "state.py"
        src.write_text("class State:\n    pass\n")
        from codeupipe.linter.check_symbols import CheckSymbols

        refs = [{
            "file": "state.py", "symbols": ["State", "Pipeline"],
            "hash": None, "exists": True, "current_hash": "abc",
            "doc_path": "DOC.md", "line": 5, "abs_path": str(src),
        }]
        result = run_filter(CheckSymbols(), {
            "directory": str(tmp_path),
            "resolved_refs": refs,
        })
        issues = result.get("symbol_issues")
        assert len(issues) == 1
        assert issues[0]["symbol"] == "Pipeline"
        assert issues[0]["file"] == "state.py"

    def test_finds_function(self, tmp_path):
        src = tmp_path / "utils.py"
        src.write_text("def build_pipeline():\n    pass\n")
        from codeupipe.linter.check_symbols import CheckSymbols

        refs = [{
            "file": "utils.py", "symbols": ["build_pipeline"],
            "hash": None, "exists": True, "current_hash": "abc",
            "doc_path": "DOC.md", "line": 1, "abs_path": str(src),
        }]
        result = run_filter(CheckSymbols(), {
            "directory": str(tmp_path),
            "resolved_refs": refs,
        })
        assert result.get("symbol_issues") == []

    def test_finds_dotted_attribute(self, tmp_path):
        """State.executed means class State with attribute/method 'executed'."""
        src = tmp_path / "state.py"
        src.write_text(
            "class State:\n"
            "    def __init__(self):\n"
            "        self.executed = []\n"
            "    def mark_executed(self, name): pass\n"
        )
        from codeupipe.linter.check_symbols import CheckSymbols

        refs = [{
            "file": "state.py",
            "symbols": ["State.executed", "State.mark_executed"],
            "hash": None, "exists": True, "current_hash": "abc",
            "doc_path": "DOC.md", "line": 1, "abs_path": str(src),
        }]
        result = run_filter(CheckSymbols(), {
            "directory": str(tmp_path),
            "resolved_refs": refs,
        })
        assert result.get("symbol_issues") == []

    def test_skips_nonexistent_files(self, tmp_path):
        from codeupipe.linter.check_symbols import CheckSymbols

        refs = [{
            "file": "ghost.py", "symbols": ["Foo"],
            "hash": None, "exists": False, "current_hash": None,
            "doc_path": "DOC.md", "line": 1, "abs_path": str(tmp_path / "ghost.py"),
        }]
        result = run_filter(CheckSymbols(), {
            "directory": str(tmp_path),
            "resolved_refs": refs,
        })
        # Missing files are a ResolveRefs concern, not CheckSymbols
        assert result.get("symbol_issues") == []

    def test_detects_missing_dotted_method(self, tmp_path):
        src = tmp_path / "state.py"
        src.write_text("class State:\n    pass\n")
        from codeupipe.linter.check_symbols import CheckSymbols

        refs = [{
            "file": "state.py",
            "symbols": ["State.nonexistent_method"],
            "hash": None, "exists": True, "current_hash": "abc",
            "doc_path": "DOC.md", "line": 1, "abs_path": str(src),
        }]
        result = run_filter(CheckSymbols(), {
            "directory": str(tmp_path),
            "resolved_refs": refs,
        })
        issues = result.get("symbol_issues")
        assert len(issues) == 1
        assert "nonexistent_method" in issues[0]["symbol"]
