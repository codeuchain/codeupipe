"""ReassembleHtml — inject obfuscated script blocks back into HTML templates."""

from typing import List

from codeupipe import Payload


class ReassembleHtml:
    """Replace script placeholders in HTML templates with obfuscated code.

    Reads:
        - ``html_templates`` — list of ``{filename, template, block_count}`` dicts.
        - ``obfuscated_blocks`` — list with ``placeholder`` and ``obfuscated_code``.

    Writes:
        - ``reassembled_html`` — list of ``{filename, content}`` dicts.
    """

    def call(self, payload: Payload) -> Payload:
        templates = payload.get("html_templates") or []
        blocks = payload.get("obfuscated_blocks") or []

        # Build placeholder → code map
        placeholder_map = {
            b["placeholder"]: b["obfuscated_code"]
            for b in blocks
        }

        results: List[dict] = []
        for tmpl in templates:
            content = tmpl["template"]
            for placeholder, code in placeholder_map.items():
                content = content.replace(placeholder, code)
            results.append({
                "filename": tmpl["filename"],
                "content": content,
            })

        return payload.insert("reassembled_html", results)
