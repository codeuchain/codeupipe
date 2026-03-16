"""Tests for ReassembleHtml — inject obfuscated scripts back into templates."""

from codeupipe import Payload
from codeupipe.deploy.obfuscate.reassemble_html import ReassembleHtml


class TestReassembleHtml:
    def test_single_replacement(self):
        templates = [{"filename": "index.html", "template": "<script>__CUP_SCRIPT_0__</script>", "block_count": 1}]
        blocks = [{"placeholder": "__CUP_SCRIPT_0__", "obfuscated_code": "var x=1;"}]

        f = ReassembleHtml()
        result = f.call(Payload({"html_templates": templates, "obfuscated_blocks": blocks}))

        html_list = result.get("reassembled_html")
        assert len(html_list) == 1
        assert html_list[0]["content"] == "<script>var x=1;</script>"

    def test_multiple_replacements(self):
        templates = [{
            "filename": "page.html",
            "template": "<script>__PH_A__</script><p>Hi</p><script>__PH_B__</script>",
            "block_count": 2,
        }]
        blocks = [
            {"placeholder": "__PH_A__", "obfuscated_code": "alert(1);"},
            {"placeholder": "__PH_B__", "obfuscated_code": "alert(2);"},
        ]

        f = ReassembleHtml()
        result = f.call(Payload({"html_templates": templates, "obfuscated_blocks": blocks}))

        content = result.get("reassembled_html")[0]["content"]
        assert "alert(1);" in content
        assert "alert(2);" in content

    def test_no_blocks(self):
        templates = [{"filename": "clean.html", "template": "<p>No scripts</p>", "block_count": 0}]

        f = ReassembleHtml()
        result = f.call(Payload({"html_templates": templates, "obfuscated_blocks": []}))

        assert result.get("reassembled_html")[0]["content"] == "<p>No scripts</p>"

    def test_preserves_filename(self):
        templates = [{"filename": "app.html", "template": "content", "block_count": 0}]

        f = ReassembleHtml()
        result = f.call(Payload({"html_templates": templates, "obfuscated_blocks": []}))

        assert result.get("reassembled_html")[0]["filename"] == "app.html"
