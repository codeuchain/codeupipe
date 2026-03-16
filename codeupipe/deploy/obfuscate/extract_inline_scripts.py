"""ExtractInlineScripts — extract inline <script> blocks from HTML for obfuscation."""

import re
from typing import List

from codeupipe import Payload


# Matches <script ...>content</script>, but NOT <script src="...">
_SCRIPT_RE = re.compile(
    r"(<script(?![^>]*\bsrc\s*=)[^>]*>)([\s\S]*?)(</script>)",
    re.IGNORECASE,
)


class ExtractInlineScripts:
    """Extract inline <script> blocks from HTML sources for separate processing.

    Reads:
        - ``html_sources`` — list of ``{filename, content, ...}`` dicts.
        - ``config`` — dict with ``min_script_length`` threshold.

    Writes:
        - ``script_blocks`` — list of ``{filename, index, open_tag, code, close_tag}`` dicts.
        - ``html_templates`` — HTML content with script bodies replaced by placeholders.
    """

    def call(self, payload: Payload) -> Payload:
        sources = payload.get("html_sources") or []
        config = payload.get("config") or {}
        min_len = config.get("min_script_length", 50)

        all_blocks: List[dict] = []
        templates: List[dict] = []

        for source in sources:
            filename = source["filename"]
            content = source["content"]
            block_idx = 0
            block_list: List[dict] = []

            def replacer(match: re.Match) -> str:
                nonlocal block_idx
                open_tag = match.group(1)
                code = match.group(2)
                close_tag = match.group(3)

                trimmed = code.strip()
                if not trimmed or len(trimmed) < min_len:
                    return match.group(0)  # keep as-is

                placeholder = f"__CUP_SCRIPT_{filename}_{block_idx}__"
                block_list.append({
                    "filename": filename,
                    "index": block_idx,
                    "open_tag": open_tag,
                    "code": trimmed,
                    "close_tag": close_tag,
                    "placeholder": placeholder,
                })
                block_idx += 1
                return f"{open_tag}{placeholder}{close_tag}"

            templated = _SCRIPT_RE.sub(replacer, content)

            all_blocks.extend(block_list)
            templates.append({
                "filename": filename,
                "template": templated,
                "block_count": len(block_list),
            })

        return (
            payload
            .insert("script_blocks", all_blocks)
            .insert("html_templates", templates)
        )
