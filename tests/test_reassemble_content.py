"""Tests for ReassembleContent (replaces ReassembleHtml) — placeholder replacement."""

import pytest

from codeupipe import Payload
from codeupipe.testing import run_filter
from codeupipe.deploy.obfuscate.reassemble_content import ReassembleContent
# Backward-compat alias
from codeupipe.deploy.obfuscate.reassemble_html import ReassembleHtml


class TestReassembleContent:
    """ReassembleContent is the renamed version — already generic."""

    def test_replaces_placeholders(self):
        templates = [{"filename": "index.html", "template": (
            "<html><script>__CUP_SCRIPT_index.html_0__</script></html>"
        ), "block_count": 1}]
        blocks = [{"placeholder": "__CUP_SCRIPT_index.html_0__", "transformed_code": "obfuscated()"}]

        result = run_filter(ReassembleContent(), {
            "templates": templates,
            "transformed_blocks": blocks,
            "config": {},
        })
        out = result.get("reassembled")
        assert len(out) == 1
        assert "obfuscated()" in out[0]["content"]

    def test_writes_backward_compat_keys(self):
        templates = [{"filename": "index.html", "template": "hello", "block_count": 0}]
        result = run_filter(ReassembleContent(), {
            "templates": templates,
            "html_templates": templates,
            "transformed_blocks": [],
            "obfuscated_blocks": [],
            "config": {},
        })
        # New key
        assert result.get("reassembled") is not None
        # Backward-compat key
        assert result.get("reassembled_html") is not None

    def test_empty_templates(self):
        result = run_filter(ReassembleContent(), {
            "templates": [],
            "transformed_blocks": [],
            "config": {},
        })
        assert result.get("reassembled") == []


class TestReassembleHtmlAlias:
    """Old name still importable and functional."""

    def test_alias_importable(self):
        assert ReassembleHtml is not None

    def test_alias_functional(self):
        templates = [{"filename": "index.html", "template": "hi", "block_count": 0}]
        result = run_filter(ReassembleHtml(), {
            "html_templates": templates,
            "obfuscated_blocks": [],
        })
        assert result.get("reassembled_html") is not None
