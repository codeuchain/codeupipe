"""Tests for ExtractInlineScripts — regex extraction of <script> blocks."""

from codeupipe import Payload
from codeupipe.deploy.obfuscate.extract_inline_scripts import ExtractInlineScripts


class TestExtractInlineScripts:
    def _make_payload(self, html, min_len=50):
        return Payload({
            "html_sources": [{"filename": "test.html", "content": html}],
            "config": {"min_script_length": min_len},
        })

    def test_extracts_inline_script(self):
        code = "function init() { console.log('hello world from the application startup'); }"
        html = f"<html><body><script>{code}</script></body></html>"

        f = ExtractInlineScripts()
        result = f.call(self._make_payload(html))

        blocks = result.get("script_blocks")
        assert len(blocks) == 1
        assert blocks[0]["code"] == code
        assert blocks[0]["filename"] == "test.html"
        assert blocks[0]["index"] == 0

    def test_skips_external_scripts(self):
        html = '<html><script src="app.js"></script></html>'
        f = ExtractInlineScripts()
        result = f.call(self._make_payload(html, min_len=0))
        assert result.get("script_blocks") == []

    def test_skips_short_scripts(self):
        html = '<html><script>x=1</script></html>'
        f = ExtractInlineScripts()
        result = f.call(self._make_payload(html, min_len=50))
        assert result.get("script_blocks") == []

    def test_multiple_blocks(self):
        code_a = "function alpha() { return 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'; }"
        code_b = "function beta() { return 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'; }"
        html = f"<html><script>{code_a}</script><script>{code_b}</script></html>"

        f = ExtractInlineScripts()
        result = f.call(self._make_payload(html))

        blocks = result.get("script_blocks")
        assert len(blocks) == 2
        assert blocks[0]["index"] == 0
        assert blocks[1]["index"] == 1

    def test_placeholder_in_template(self):
        code = "function init() { console.log('hello world from the application startup'); }"
        html = f"<html><script>{code}</script></html>"

        f = ExtractInlineScripts()
        result = f.call(self._make_payload(html))

        templates = result.get("html_templates")
        assert len(templates) == 1
        assert "__CUP_SCRIPT_" in templates[0]["template"]
        assert code not in templates[0]["template"]

    def test_preserves_open_close_tags(self):
        code = "function init() { console.log('hello world from the application startup'); }"
        html = f'<html><script type="module">{code}</script></html>'

        f = ExtractInlineScripts()
        result = f.call(self._make_payload(html))

        block = result.get("script_blocks")[0]
        assert 'type="module"' in block["open_tag"]
        assert block["close_tag"] == "</script>"

    def test_empty_sources(self):
        f = ExtractInlineScripts()
        result = f.call(Payload({
            "html_sources": [],
            "config": {"min_script_length": 50},
        }))
        assert result.get("script_blocks") == []
        assert result.get("html_templates") == []
