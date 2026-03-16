"""MinifyHtml — backward-compat alias for MinifyContent."""

import re

from codeupipe import Payload
from .minify_content import MinifyContent


class MinifyHtml:
    """Minify HTML content after script blocks have been re-injected.

    .. deprecated::
        Use :class:`MinifyContent` instead. This class delegates to it
        and ensures ``minified_html`` / ``minify_stats`` are always written.

    Reads:
        - ``reassembled_html`` — list of ``{filename, content}`` dicts.
        - ``config`` — dict with ``html_opts``.

    Writes:
        - ``minified_html`` — list of ``{filename, content, original_size, minified_size}`` dicts.
        - ``minify_stats`` — dict with totals.
        - ``minified`` — new canonical key (same data).
    """

    def __init__(self, *, strict: bool = False):
        self._delegate = MinifyContent(strict=strict)

    def call(self, payload: Payload) -> Payload:
        return self._delegate.call(payload)


def _fallback_minify(content: str) -> str:
    """Lightweight fallback: collapse whitespace, strip HTML comments.

    Kept here for backward-compat — tests may import this directly.
    """
    content = re.sub(r"<!--(?!\[).*?-->", "", content, flags=re.DOTALL)
    content = re.sub(r"\s+", " ", content)
    content = re.sub(r">\s+<", "><", content)
    return content.strip()
