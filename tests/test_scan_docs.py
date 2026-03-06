"""Tests for ScanDocs filter — extracts cup:ref markers from .md files."""

from pathlib import Path

from codeupipe import Payload
from codeupipe.testing import run_filter


class TestScanDocs:
    """ScanDocs: parse markdown files and extract cup:ref markers."""

    def test_extracts_single_marker(self, tmp_path):
        md = tmp_path / "README.md"
        md.write_text(
            "# Title\n"
            "<!-- cup:ref file=src/state.py symbols=State.executed -->\n"
            "| `state.executed` | list |\n"
            "<!-- /cup:ref -->\n"
        )
        from codeupipe.linter.scan_docs import ScanDocs

        result = run_filter(ScanDocs(), {"directory": str(tmp_path)})
        refs = result.get("doc_refs")
        assert len(refs) == 1
        assert refs[0]["file"] == "src/state.py"
        assert refs[0]["symbols"] == ["State.executed"]
        assert refs[0]["doc_path"] == str(md)

    def test_extracts_multiple_markers_from_one_file(self, tmp_path):
        md = tmp_path / "CONCEPTS.md"
        md.write_text(
            "<!-- cup:ref file=src/a.py symbols=Foo -->\n"
            "text\n"
            "<!-- /cup:ref -->\n"
            "gap\n"
            "<!-- cup:ref file=src/b.py hash=abc123 -->\n"
            "more text\n"
            "<!-- /cup:ref -->\n"
        )
        from codeupipe.linter.scan_docs import ScanDocs

        result = run_filter(ScanDocs(), {"directory": str(tmp_path)})
        refs = result.get("doc_refs")
        assert len(refs) == 2
        assert refs[0]["file"] == "src/a.py"
        assert refs[1]["file"] == "src/b.py"
        assert refs[1]["hash"] == "abc123"

    def test_extracts_from_multiple_files(self, tmp_path):
        (tmp_path / "A.md").write_text(
            "<!-- cup:ref file=x.py -->\nstuff\n<!-- /cup:ref -->\n"
        )
        (tmp_path / "B.md").write_text(
            "<!-- cup:ref file=y.py -->\nstuff\n<!-- /cup:ref -->\n"
        )
        from codeupipe.linter.scan_docs import ScanDocs

        result = run_filter(ScanDocs(), {"directory": str(tmp_path)})
        refs = result.get("doc_refs")
        files = {r["file"] for r in refs}
        assert files == {"x.py", "y.py"}

    def test_no_markers_returns_empty(self, tmp_path):
        (tmp_path / "README.md").write_text("# Plain doc\nNo markers here.\n")
        from codeupipe.linter.scan_docs import ScanDocs

        result = run_filter(ScanDocs(), {"directory": str(tmp_path)})
        assert result.get("doc_refs") == []

    def test_no_md_files_returns_empty(self, tmp_path):
        (tmp_path / "code.py").write_text("x = 1\n")
        from codeupipe.linter.scan_docs import ScanDocs

        result = run_filter(ScanDocs(), {"directory": str(tmp_path)})
        assert result.get("doc_refs") == []

    def test_captures_line_number(self, tmp_path):
        md = tmp_path / "DOC.md"
        md.write_text(
            "line1\nline2\n"
            "<!-- cup:ref file=src/core.py -->\n"
            "content\n"
            "<!-- /cup:ref -->\n"
        )
        from codeupipe.linter.scan_docs import ScanDocs

        result = run_filter(ScanDocs(), {"directory": str(tmp_path)})
        refs = result.get("doc_refs")
        assert refs[0]["line"] == 3

    def test_marker_without_symbols_or_hash(self, tmp_path):
        md = tmp_path / "DOC.md"
        md.write_text(
            "<!-- cup:ref file=src/pipeline.py -->\n"
            "content\n"
            "<!-- /cup:ref -->\n"
        )
        from codeupipe.linter.scan_docs import ScanDocs

        result = run_filter(ScanDocs(), {"directory": str(tmp_path)})
        refs = result.get("doc_refs")
        assert refs[0]["symbols"] == []
        assert refs[0]["hash"] is None
