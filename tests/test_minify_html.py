"""Tests for MinifyHtml — HTML minification via subprocess with fallback."""

from unittest.mock import patch

from codeupipe import Payload
from codeupipe.deploy.obfuscate.minify_html import MinifyHtml, _fallback_minify


class TestMinifyHtml:
    def _make_payload(self, html_list):
        return Payload({
            "reassembled_html": html_list,
            "config": {"html_opts": {}},
        })

    @patch("codeupipe.deploy.obfuscate.minify_content._find_minifier")
    def test_fallback_when_no_tool(self, mock_find):
        """Uses lightweight fallback when html-minifier-terser not installed."""
        mock_find.return_value = ""
        html_list = [{"filename": "index.html", "content": "<p>   Hello   </p>  <p>  World  </p>"}]

        f = MinifyHtml(strict=False)
        result = f.call(self._make_payload(html_list))

        minified = result.get("minified_html")
        assert len(minified) == 1
        # Fallback collapses whitespace
        assert "   " not in minified[0]["content"]
        assert minified[0]["minified_size"] <= minified[0]["original_size"]

    @patch("codeupipe.deploy.obfuscate.minify_content._find_minifier")
    def test_strict_mode_raises(self, mock_find):
        """When strict=True and no tool, raise RuntimeError."""
        mock_find.return_value = ""
        import pytest
        f = MinifyHtml(strict=True)
        with pytest.raises(RuntimeError, match="html-minifier-terser not found"):
            f.call(self._make_payload([{"filename": "x.html", "content": "<p>x</p>"}]))

    @patch("codeupipe.deploy.obfuscate.minify_content._find_minifier")
    @patch("codeupipe.deploy.obfuscate.minify_content._minify_one")
    def test_successful_minification(self, mock_minify, mock_find):
        mock_find.return_value = "/usr/bin/html-minifier-terser"
        mock_minify.return_value = "<p>Hello</p><p>World</p>"

        html_list = [{"filename": "index.html", "content": "<p>  Hello  </p>  <p>  World  </p>"}]
        f = MinifyHtml()
        result = f.call(self._make_payload(html_list))

        minified = result.get("minified_html")
        assert minified[0]["content"] == "<p>Hello</p><p>World</p>"

    def test_stats_computed(self):
        html_list = [
            {"filename": "a.html", "content": "<p>    big    spaces    </p>"},
            {"filename": "b.html", "content": "<p>  more  spaces  </p>"},
        ]

        with patch("codeupipe.deploy.obfuscate.minify_content._find_minifier", return_value=""):
            f = MinifyHtml()
            result = f.call(self._make_payload(html_list))

        stats = result.get("minify_stats")
        assert stats["total_original"] > 0
        assert stats["total_minified"] > 0
        assert stats["ratio"] > 0

    def test_empty_input(self):
        f = MinifyHtml()
        result = f.call(self._make_payload([]))
        assert result.get("minified_html") == []
        assert result.get("minify_stats")["total_original"] == 0


class TestFallbackMinify:
    def test_removes_html_comments(self):
        result = _fallback_minify("<p>a</p><!-- comment --><p>b</p>")
        assert "comment" not in result
        assert "<p>" in result

    def test_collapses_whitespace(self):
        result = _fallback_minify("<p>   lots   of   space   </p>")
        assert "   " not in result

    def test_removes_space_between_tags(self):
        result = _fallback_minify("<p>a</p>   \n   <p>b</p>")
        assert "><" in result
