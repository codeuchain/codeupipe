"""Tests for ScanHtmlFiles — discover HTML files in source directory."""

import os
import tempfile

import pytest

from codeupipe import Payload
from codeupipe.deploy.obfuscate.scan_html_files import ScanHtmlFiles


class TestScanHtmlFiles:
    def test_auto_detect_html(self, tmp_path):
        # Create HTML files
        (tmp_path / "index.html").write_text("<h1>Hello</h1>")
        (tmp_path / "about.html").write_text("<h1>About</h1>")
        (tmp_path / "style.css").write_text("body {}")  # not HTML
        (tmp_path / "app.js").write_text("// js")  # not HTML

        f = ScanHtmlFiles()
        result = f.call(Payload({"config": {"src_dir": str(tmp_path)}}))

        sources = result.get("html_sources")
        assert len(sources) == 2
        filenames = [s["filename"] for s in sources]
        assert "index.html" in filenames
        assert "about.html" in filenames

    def test_explicit_file_list(self, tmp_path):
        (tmp_path / "index.html").write_text("<h1>Hello</h1>")
        (tmp_path / "admin.html").write_text("<h1>Admin</h1>")

        f = ScanHtmlFiles()
        result = f.call(Payload({
            "config": {
                "src_dir": str(tmp_path),
                "html_files": ["index.html"],
            },
        }))

        sources = result.get("html_sources")
        assert len(sources) == 1
        assert sources[0]["filename"] == "index.html"

    def test_includes_content_and_size(self, tmp_path):
        content = "<html><body>Test</body></html>"
        (tmp_path / "page.html").write_text(content)

        f = ScanHtmlFiles()
        result = f.call(Payload({"config": {"src_dir": str(tmp_path)}}))

        src = result.get("html_sources")[0]
        assert src["content"] == content
        assert src["size"] == len(content.encode("utf-8"))
        assert src["path"].endswith("page.html")

    def test_missing_dir_raises(self):
        f = ScanHtmlFiles()
        with pytest.raises(FileNotFoundError, match="not found"):
            f.call(Payload({"config": {"src_dir": "/nonexistent/path"}}))

    def test_empty_dir(self, tmp_path):
        f = ScanHtmlFiles()
        result = f.call(Payload({"config": {"src_dir": str(tmp_path)}}))
        assert result.get("html_sources") == []

    def test_skips_missing_explicit_files(self, tmp_path):
        (tmp_path / "exists.html").write_text("<p>yes</p>")

        f = ScanHtmlFiles()
        result = f.call(Payload({
            "config": {
                "src_dir": str(tmp_path),
                "html_files": ["exists.html", "ghost.html"],
            },
        }))

        sources = result.get("html_sources")
        assert len(sources) == 1
        assert sources[0]["filename"] == "exists.html"
