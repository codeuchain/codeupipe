"""ExtractEmbeddedCode — extract inline code blocks from source files for processing."""

import re
from typing import Any, Dict, List, Optional

from codeupipe import Payload


# Default: extract <script> blocks (excluding external src=)
_DEFAULT_EXTRACT_PATTERNS = [
    {"tag": "script", "exclude_attr": "src"},
]


def _build_tag_regex(tag: str, exclude_attr: Optional[str] = None) -> re.Pattern:
    """Build a regex that matches <tag ...>content</tag>.

    Args:
        tag: HTML tag name (e.g. "script", "style").
        exclude_attr: If set, skip tags that have this attribute.
    """
    if exclude_attr:
        pattern = (
            rf"(<{tag}(?![^>]*\b{re.escape(exclude_attr)}\s*=)[^>]*>)"
            rf"([\s\S]*?)"
            rf"(</{tag}>)"
        )
    else:
        pattern = (
            rf"(<{tag}[^>]*>)"
            rf"([\s\S]*?)"
            rf"(</{tag}>)"
        )
    return re.compile(pattern, re.IGNORECASE)


class ExtractEmbeddedCode:
    """Extract inline code blocks from source files for separate processing.

    Generalizes ExtractInlineScripts to support configurable extraction
    patterns per file type (e.g. <style> blocks, PHP tags).

    Reads:
        - ``sources`` (or ``html_sources``) — list of ``{filename, content}`` dicts.
        - ``config`` — dict with ``min_script_length``, ``file_types``.

    Writes:
        - ``code_blocks`` — list of ``{filename, index, open_tag, code, close_tag, placeholder}``.
        - ``templates`` — source content with code replaced by placeholders.
        - ``script_blocks`` — backward-compat alias for code_blocks.
        - ``html_templates`` — backward-compat alias for templates.
    """

    def call(self, payload: Payload) -> Payload:
        # Read from new key first, fall back to old key
        sources = payload.get("sources") or payload.get("html_sources") or []
        config = payload.get("config") or {}
        min_len = config.get("min_script_length", 50)
        file_types = config.get("file_types") or []

        # Collect extraction patterns from file_types config
        extract_patterns = _DEFAULT_EXTRACT_PATTERNS
        for ft in file_types:
            patterns = ft.get("extract_patterns")
            if patterns is not None:
                extract_patterns = patterns
                break  # Use first file type's patterns (TODO: per-extension dispatch)

        # Build regex list from patterns
        regexes = []
        for pat in extract_patterns:
            if isinstance(pat, dict):
                tag = pat.get("tag", "script")
                exclude = pat.get("exclude_attr")
                regexes.append(_build_tag_regex(tag, exclude))
            elif isinstance(pat, str):
                regexes.append(re.compile(pat, re.IGNORECASE | re.DOTALL))

        # If no patterns configured, use default script extraction
        if not regexes:
            regexes = [_build_tag_regex("script", "src")]

        all_blocks: List[dict] = []
        templates: List[dict] = []

        for source in sources:
            filename = source["filename"]
            content = source["content"]
            block_idx = 0
            block_list: List[dict] = []

            for regex in regexes:
                def make_replacer(regex_obj: re.Pattern) -> Any:
                    def replacer(match: re.Match) -> str:
                        nonlocal block_idx
                        open_tag = match.group(1)
                        code = match.group(2)
                        close_tag = match.group(3)

                        trimmed = code.strip()
                        if not trimmed or len(trimmed) < min_len:
                            return match.group(0)

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
                    return replacer

                content = regex.sub(make_replacer(regex), content)

            all_blocks.extend(block_list)
            templates.append({
                "filename": filename,
                "template": content,
                "block_count": len(block_list),
            })

        return (
            payload
            .insert("code_blocks", all_blocks)
            .insert("templates", templates)
            .insert("script_blocks", all_blocks)       # backward compat
            .insert("html_templates", templates)        # backward compat
        )
