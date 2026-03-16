"""ReassembleContent — inject processed code blocks back into source templates."""

from typing import List

from codeupipe import Payload


class ReassembleContent:
    """Replace code placeholders in templates with transformed code.

    Generalized from ReassembleHtml — works with any placeholder format.

    Reads:
        - ``templates`` (or ``html_templates``) — list of ``{filename, template}`` dicts.
        - ``transformed_blocks`` (or ``obfuscated_blocks``) — list with ``placeholder``
          and ``transformed_code`` (or ``obfuscated_code``).

    Writes:
        - ``reassembled`` — list of ``{filename, content}`` dicts.
        - ``reassembled_html`` — backward-compat alias.
    """

    def call(self, payload: Payload) -> Payload:
        templates = payload.get("templates") or payload.get("html_templates") or []
        blocks = (
            payload.get("transformed_blocks")
            or payload.get("obfuscated_blocks")
            or []
        )

        # Build placeholder → code map
        # Support both new and old key names
        placeholder_map = {}
        for b in blocks:
            placeholder = b.get("placeholder", "")
            code = b.get("transformed_code") or b.get("obfuscated_code", "")
            if placeholder:
                placeholder_map[placeholder] = code

        results: List[dict] = []
        for tmpl in templates:
            content = tmpl["template"]
            for placeholder, code in placeholder_map.items():
                content = content.replace(placeholder, code)
            results.append({
                "filename": tmpl["filename"],
                "content": content,
            })

        return (
            payload
            .insert("reassembled", results)
            .insert("reassembled_html", results)  # backward compat
        )
