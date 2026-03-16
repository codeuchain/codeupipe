"""Tests for MinifyContent — pluggable minifier per file type (replaces MinifyHtml)."""

import pytest

from codeupipe import Payload
from codeupipe.testing import run_filter
from codeupipe.deploy.obfuscate.minify_content import MinifyContent
# Backward-compat alias
from codeupipe.deploy.obfuscate.minify_html import MinifyHtml


class TestMinifyContent:
    """MinifyContent generalizes minification to configurable tools per file type."""

    def test_fallback_minifies_html(self):
        html_list = [{"filename": "index.html", "content": (
            "<html> <head> </head> <body>  <!-- comment -->  <p> hello </p> </body> </html>"
        )}]
        result = run_filter(MinifyContent(strict=False), {
            "reassembled": html_list,
            "config": {"html_opts": {}},
        })
        out = result.get("minified")
        assert len(out) == 1
        # Minified should be shorter
        assert out[0]["minified_size"] <= out[0]["original_size"]

    def test_writes_backward_compat_keys(self):
        html_list = [{"filename": "index.html", "content": "<html></html>"}]
        result = run_filter(MinifyContent(strict=False), {
            "reassembled": html_list,
            "reassembled_html": html_list,
            "config": {"html_opts": {}},
        })
        # New keys
        assert result.get("minified") is not None
        assert result.get("minify_content_stats") is not None or result.get("minify_stats") is not None
        # Backward-compat keys
        assert result.get("minified_html") is not None

    def test_stats_structure(self):
        html_list = [{"filename": "index.html", "content": "<html> </html>"}]
        result = run_filter(MinifyContent(strict=False), {
            "reassembled": html_list,
            "config": {"html_opts": {}},
        })
        stats = result.get("minify_stats")
        assert "total_original" in stats
        assert "total_minified" in stats
        assert "ratio" in stats

    def test_empty_input(self):
        result = run_filter(MinifyContent(strict=False), {
            "reassembled": [],
            "config": {"html_opts": {}},
        })
        assert result.get("minified") == []


class TestMinifyHtmlAlias:
    """Old name still importable and functional."""

    def test_alias_importable(self):
        assert MinifyHtml is not None

    def test_alias_produces_minified_html(self):
        html_list = [{"filename": "index.html", "content": "<html> </html>"}]
        result = run_filter(MinifyHtml(strict=False), {
            "reassembled_html": html_list,
            "config": {"html_opts": {}},
        })
        assert result.get("minified_html") is not None
