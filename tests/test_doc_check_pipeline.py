"""Tests for the doc-check pipeline — end-to-end integration."""

from pathlib import Path

from codeupipe import Payload
from codeupipe.testing import run_pipeline, assert_payload


class TestDocCheckPipeline:
    """Integration: doc-check pipeline scans docs, resolves, checks, reports."""

    def test_clean_project(self, tmp_path):
        """All markers are in sync — report status ok."""
        import hashlib

        # Source file
        src = tmp_path / "state.py"
        src.write_text("class State:\n    executed = []\n")
        current_hash = hashlib.sha256(src.read_bytes()).hexdigest()[:7]

        # Doc with matching hash and symbol
        md = tmp_path / "README.md"
        md.write_text(
            f"<!-- cup:ref file=state.py symbols=State hash={current_hash} -->\n"
            "State tracks execution.\n"
            "<!-- /cup:ref -->\n"
        )

        from codeupipe.linter.doc_check_pipeline import build_doc_check_pipeline

        pipeline = build_doc_check_pipeline()
        result = run_pipeline(pipeline, {"directory": str(tmp_path)})
        report = result.get("doc_report")
        assert report["status"] == "ok"
        assert report["drifted"] == 0
        assert report["missing_symbols"] == 0

    def test_stale_hash(self, tmp_path):
        """Hash mismatch is detected."""
        src = tmp_path / "state.py"
        src.write_text("class State:\n    pass\n")

        md = tmp_path / "README.md"
        md.write_text(
            "<!-- cup:ref file=state.py hash=oldold1 -->\n"
            "State info.\n"
            "<!-- /cup:ref -->\n"
        )

        from codeupipe.linter.doc_check_pipeline import build_doc_check_pipeline

        pipeline = build_doc_check_pipeline()
        result = run_pipeline(pipeline, {"directory": str(tmp_path)})
        report = result.get("doc_report")
        assert report["status"] == "stale"
        assert report["drifted"] >= 1

    def test_missing_symbol(self, tmp_path):
        """Symbol that doesn't exist in source is flagged."""
        src = tmp_path / "state.py"
        src.write_text("class State:\n    pass\n")

        md = tmp_path / "README.md"
        md.write_text(
            "<!-- cup:ref file=state.py symbols=State,Pipeline -->\n"
            "State and Pipeline.\n"
            "<!-- /cup:ref -->\n"
        )

        from codeupipe.linter.doc_check_pipeline import build_doc_check_pipeline

        pipeline = build_doc_check_pipeline()
        result = run_pipeline(pipeline, {"directory": str(tmp_path)})
        report = result.get("doc_report")
        assert report["missing_symbols"] >= 1

    def test_missing_file(self, tmp_path):
        """Referenced file that doesn't exist."""
        md = tmp_path / "README.md"
        md.write_text(
            "<!-- cup:ref file=nonexistent.py hash=abc1234 -->\n"
            "Ghost reference.\n"
            "<!-- /cup:ref -->\n"
        )

        from codeupipe.linter.doc_check_pipeline import build_doc_check_pipeline

        pipeline = build_doc_check_pipeline()
        result = run_pipeline(pipeline, {"directory": str(tmp_path)})
        report = result.get("doc_report")
        assert report["missing_files"] >= 1
        assert report["status"] == "stale"

    def test_no_markers_is_clean(self, tmp_path):
        """No markers at all — report is clean."""
        (tmp_path / "README.md").write_text("# Title\nJust text.\n")

        from codeupipe.linter.doc_check_pipeline import build_doc_check_pipeline

        pipeline = build_doc_check_pipeline()
        result = run_pipeline(pipeline, {"directory": str(tmp_path)})
        report = result.get("doc_report")
        assert report["status"] == "ok"
        assert report["total_refs"] == 0
