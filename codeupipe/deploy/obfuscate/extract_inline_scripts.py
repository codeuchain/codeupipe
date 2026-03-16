"""ExtractInlineScripts — backward-compat alias for ExtractEmbeddedCode."""

from codeupipe import Payload
from .extract_embedded_code import ExtractEmbeddedCode


class ExtractInlineScripts:
    """Extract inline <script> blocks from HTML sources for separate processing.

    .. deprecated::
        Use :class:`ExtractEmbeddedCode` instead. This class delegates to it
        and ensures ``script_blocks`` / ``html_templates`` are always written.

    Reads:
        - ``html_sources`` — list of ``{filename, content, ...}`` dicts.
        - ``config`` — dict with ``min_script_length`` threshold.

    Writes:
        - ``script_blocks`` — list of block dicts.
        - ``html_templates`` — HTML with placeholders.
        - ``code_blocks`` — new canonical key (same data).
        - ``templates`` — new canonical key (same data).
    """

    def __init__(self) -> None:
        self._delegate = ExtractEmbeddedCode()

    def call(self, payload: Payload) -> Payload:
        # Ensure sources key exists from html_sources
        if not payload.get("sources") and payload.get("html_sources"):
            payload = payload.insert("sources", payload.get("html_sources"))
        return self._delegate.call(payload)
