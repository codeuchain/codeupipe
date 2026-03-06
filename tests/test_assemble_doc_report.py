"""Tests for AssembleDocReport filter — format doc-check findings into report."""

from codeupipe import Payload
from codeupipe.testing import run_filter


class TestAssembleDocReport:
    """AssembleDocReport: merge all findings into a structured report."""

    def test_clean_report(self):
        from codeupipe.linter.assemble_doc_report import AssembleDocReport

        result = run_filter(AssembleDocReport(), {
            "doc_refs": [
                {"file": "state.py", "symbols": ["State"], "hash": "abc1234",
                 "doc_path": "DOC.md", "line": 5},
            ],
            "resolved_refs": [
                {"file": "state.py", "exists": True, "current_hash": "abc1234",
                 "hash": "abc1234", "symbols": ["State"],
                 "doc_path": "DOC.md", "line": 5, "abs_path": "/x/state.py"},
            ],
            "drifted_refs": [],
            "symbol_issues": [],
        })
        report = result.get("doc_report")
        assert report["total_refs"] == 1
        assert report["drifted"] == 0
        assert report["missing_symbols"] == 0
        assert report["missing_files"] == 0
        assert report["status"] == "ok"

    def test_report_with_drift(self):
        from codeupipe.linter.assemble_doc_report import AssembleDocReport

        result = run_filter(AssembleDocReport(), {
            "doc_refs": [
                {"file": "a.py", "symbols": [], "hash": "old",
                 "doc_path": "DOC.md", "line": 1},
            ],
            "resolved_refs": [
                {"file": "a.py", "exists": True, "current_hash": "new",
                 "hash": "old", "symbols": [],
                 "doc_path": "DOC.md", "line": 1, "abs_path": "/x/a.py"},
            ],
            "drifted_refs": [
                {"file": "a.py", "stored_hash": "old", "current_hash": "new",
                 "doc_path": "DOC.md", "line": 1},
            ],
            "symbol_issues": [],
        })
        report = result.get("doc_report")
        assert report["drifted"] == 1
        assert report["status"] == "stale"

    def test_report_with_missing_symbols(self):
        from codeupipe.linter.assemble_doc_report import AssembleDocReport

        result = run_filter(AssembleDocReport(), {
            "doc_refs": [
                {"file": "a.py", "symbols": ["Foo", "Bar"], "hash": None,
                 "doc_path": "DOC.md", "line": 1},
            ],
            "resolved_refs": [
                {"file": "a.py", "exists": True, "current_hash": "abc",
                 "hash": None, "symbols": ["Foo", "Bar"],
                 "doc_path": "DOC.md", "line": 1, "abs_path": "/x/a.py"},
            ],
            "drifted_refs": [],
            "symbol_issues": [
                {"symbol": "Bar", "file": "a.py", "doc_path": "DOC.md", "line": 1},
            ],
        })
        report = result.get("doc_report")
        assert report["missing_symbols"] == 1
        assert report["status"] == "stale"

    def test_report_with_missing_file(self):
        from codeupipe.linter.assemble_doc_report import AssembleDocReport

        result = run_filter(AssembleDocReport(), {
            "doc_refs": [
                {"file": "gone.py", "symbols": [], "hash": "old",
                 "doc_path": "DOC.md", "line": 1},
            ],
            "resolved_refs": [
                {"file": "gone.py", "exists": False, "current_hash": None,
                 "hash": "old", "symbols": [],
                 "doc_path": "DOC.md", "line": 1, "abs_path": "/x/gone.py"},
            ],
            "drifted_refs": [
                {"file": "gone.py", "stored_hash": "old", "current_hash": None,
                 "doc_path": "DOC.md", "line": 1},
            ],
            "symbol_issues": [],
        })
        report = result.get("doc_report")
        assert report["missing_files"] == 1
        assert report["status"] == "stale"

    def test_report_includes_details(self):
        from codeupipe.linter.assemble_doc_report import AssembleDocReport

        result = run_filter(AssembleDocReport(), {
            "doc_refs": [
                {"file": "a.py", "symbols": ["Foo"], "hash": "old",
                 "doc_path": "DOC.md", "line": 3},
            ],
            "resolved_refs": [
                {"file": "a.py", "exists": True, "current_hash": "new",
                 "hash": "old", "symbols": ["Foo"],
                 "doc_path": "DOC.md", "line": 3, "abs_path": "/x/a.py"},
            ],
            "drifted_refs": [
                {"file": "a.py", "stored_hash": "old", "current_hash": "new",
                 "doc_path": "DOC.md", "line": 3},
            ],
            "symbol_issues": [
                {"symbol": "Foo", "file": "a.py", "doc_path": "DOC.md", "line": 3},
            ],
        })
        report = result.get("doc_report")
        assert "details" in report
        assert len(report["details"]) > 0

    def test_empty_refs(self):
        from codeupipe.linter.assemble_doc_report import AssembleDocReport

        result = run_filter(AssembleDocReport(), {
            "doc_refs": [],
            "resolved_refs": [],
            "drifted_refs": [],
            "symbol_issues": [],
        })
        report = result.get("doc_report")
        assert report["total_refs"] == 0
        assert report["status"] == "ok"
