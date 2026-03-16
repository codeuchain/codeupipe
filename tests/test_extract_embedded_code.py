"""Tests for ExtractEmbeddedCode — configurable extraction patterns (replaces ExtractInlineScripts)."""

import pytest

from codeupipe import Payload
from codeupipe.testing import run_filter
from codeupipe.deploy.obfuscate.extract_embedded_code import ExtractEmbeddedCode
# Backward-compat alias
from codeupipe.deploy.obfuscate.extract_inline_scripts import ExtractInlineScripts


class TestExtractEmbeddedCode:
    """ExtractEmbeddedCode generalizes extraction to configurable patterns."""

    def test_extracts_script_blocks_by_default(self):
        sources = [{"filename": "index.html", "content": (
            "<html><head><script>var x = 'long enough to pass the min threshold';"
            " var y = 42; var z = x + y;</script></head></html>"
        )}]
        result = run_filter(ExtractEmbeddedCode(), {
            "sources": sources,
            "config": {"min_script_length": 10},
        })
        blocks = result.get("code_blocks")
        assert len(blocks) == 1
        assert blocks[0]["code"].strip()

    def test_extracts_style_blocks_when_configured(self):
        sources = [{"filename": "index.html", "content": (
            "<html><head><style>.big { font-size: 100px; color: red; "
            "background: blue; margin: 0; padding: 0; }</style></head></html>"
        )}]
        result = run_filter(ExtractEmbeddedCode(), {
            "sources": sources,
            "config": {
                "min_script_length": 10,
                "file_types": [{
                    "extensions": [".html"],
                    "extract_patterns": [
                        {"tag": "style", "exclude_attr": None},
                    ],
                }],
            },
        })
        blocks = result.get("code_blocks")
        assert len(blocks) >= 1
        assert ".big" in blocks[0]["code"]

    def test_skips_short_blocks(self):
        sources = [{"filename": "index.html", "content": (
            "<html><script>x=1</script></html>"
        )}]
        result = run_filter(ExtractEmbeddedCode(), {
            "sources": sources,
            "config": {"min_script_length": 50},
        })
        blocks = result.get("code_blocks")
        assert len(blocks) == 0

    def test_placeholder_format(self):
        sources = [{"filename": "index.html", "content": (
            "<html><script>" + "x" * 60 + "</script></html>"
        )}]
        result = run_filter(ExtractEmbeddedCode(), {
            "sources": sources,
            "config": {"min_script_length": 10},
        })
        templates = result.get("templates")
        assert "__CUP_" in templates[0]["template"]

    def test_writes_backward_compat_keys(self):
        """Still writes script_blocks and html_templates for backward compat."""
        sources = [{"filename": "index.html", "content": (
            "<html><script>" + "x" * 60 + "</script></html>"
        )}]
        result = run_filter(ExtractEmbeddedCode(), {
            "sources": sources,
            "html_sources": sources,
            "config": {"min_script_length": 10},
        })
        # New keys
        assert result.get("code_blocks") is not None
        assert result.get("templates") is not None
        # Backward-compat keys
        assert result.get("script_blocks") is not None
        assert result.get("html_templates") is not None

    def test_excludes_external_script_src(self):
        sources = [{"filename": "index.html", "content": (
            '<html><script src="cdn.js"></script>'
            '<script>' + 'x' * 60 + '</script></html>'
        )}]
        result = run_filter(ExtractEmbeddedCode(), {
            "sources": sources,
            "config": {"min_script_length": 10},
        })
        blocks = result.get("code_blocks")
        assert len(blocks) == 1  # only the inline one


class TestExtractInlineScriptsAlias:
    """Old name still importable and functional."""

    def test_alias_importable(self):
        assert ExtractInlineScripts is not None

    def test_alias_functional(self):
        sources = [{"filename": "index.html", "content": (
            "<html><script>" + "x" * 60 + "</script></html>"
        )}]
        result = run_filter(ExtractInlineScripts(), {
            "html_sources": sources,
            "config": {"min_script_length": 10},
        })
        assert result.get("script_blocks") is not None
