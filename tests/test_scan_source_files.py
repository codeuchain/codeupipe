"""Tests for ScanSourceFiles — configurable file type scanning (replaces ScanHtmlFiles)."""

import os

import pytest

from codeupipe import Payload
from codeupipe.testing import run_filter
from codeupipe.deploy.obfuscate.scan_source_files import ScanSourceFiles
# Backward-compat alias
from codeupipe.deploy.obfuscate.scan_html_files import ScanHtmlFiles


class TestScanSourceFiles:
    """ScanSourceFiles generalizes file scanning to any configured extensions."""

    def test_scans_html_by_default(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>")
        (tmp_path / "app.js").write_text("console.log('hi')")

        result = run_filter(ScanSourceFiles(), {
            "config": {"src_dir": str(tmp_path), "file_types": [{"extensions": [".html"]}]},
        })
        sources = result.get("sources")
        assert len(sources) == 1
        assert sources[0]["filename"] == "index.html"

    def test_scans_multiple_extensions(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>")
        (tmp_path / "page.htm").write_text("<html></html>")
        (tmp_path / "app.js").write_text("console.log('hi')")

        result = run_filter(ScanSourceFiles(), {
            "config": {
                "src_dir": str(tmp_path),
                "file_types": [{"extensions": [".html", ".htm"]}],
            },
        })
        sources = result.get("sources")
        filenames = [s["filename"] for s in sources]
        assert "index.html" in filenames
        assert "page.htm" in filenames
        assert "app.js" not in filenames

    def test_scans_php_files(self, tmp_path):
        (tmp_path / "index.php").write_text("<?php echo 'hi'; ?>")

        result = run_filter(ScanSourceFiles(), {
            "config": {
                "src_dir": str(tmp_path),
                "file_types": [{"extensions": [".php"]}],
            },
        })
        sources = result.get("sources")
        assert len(sources) == 1
        assert sources[0]["filename"] == "index.php"

    def test_explicit_file_list(self, tmp_path):
        (tmp_path / "a.html").write_text("<html>A</html>")
        (tmp_path / "b.html").write_text("<html>B</html>")

        result = run_filter(ScanSourceFiles(), {
            "config": {
                "src_dir": str(tmp_path),
                "html_files": ["a.html"],
                "file_types": [{"extensions": [".html"]}],
            },
        })
        sources = result.get("sources")
        assert len(sources) == 1
        assert sources[0]["filename"] == "a.html"

    def test_missing_src_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            run_filter(ScanSourceFiles(), {
                "config": {"src_dir": "/nonexistent", "file_types": [{"extensions": [".html"]}]},
            })

    def test_source_dict_fields(self, tmp_path):
        (tmp_path / "index.html").write_text("<h1>Hello</h1>")

        result = run_filter(ScanSourceFiles(), {
            "config": {
                "src_dir": str(tmp_path),
                "file_types": [{"extensions": [".html"]}],
            },
        })
        source = result.get("sources")[0]
        assert "filename" in source
        assert "path" in source
        assert "content" in source
        assert "size" in source

    def test_also_writes_html_sources_for_backward_compat(self, tmp_path):
        """ScanSourceFiles writes both 'sources' and 'html_sources' keys."""
        (tmp_path / "index.html").write_text("<html></html>")

        result = run_filter(ScanSourceFiles(), {
            "config": {
                "src_dir": str(tmp_path),
                "file_types": [{"extensions": [".html"]}],
            },
        })
        # New key
        assert result.get("sources") is not None
        # Backward-compat key
        assert result.get("html_sources") is not None


class TestScanHtmlFilesAlias:
    """ScanHtmlFiles still works as an alias for backward compatibility."""

    def test_scan_html_files_still_importable(self):
        """The old class name must still be importable."""
        assert ScanHtmlFiles is not None

    def test_scan_html_files_produces_html_sources(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>")

        result = run_filter(ScanHtmlFiles(), {
            "config": {"src_dir": str(tmp_path)},
        })
        assert result.get("html_sources") is not None
