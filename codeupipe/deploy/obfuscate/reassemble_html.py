"""ReassembleHtml — backward-compat alias for ReassembleContent."""

from codeupipe import Payload
from .reassemble_content import ReassembleContent


class ReassembleHtml:
    """Replace script placeholders in HTML templates with obfuscated code.

    .. deprecated::
        Use :class:`ReassembleContent` instead. This class delegates to it
        and ensures ``reassembled_html`` is always written.

    Reads:
        - ``html_templates`` — list of ``{filename, template, block_count}`` dicts.
        - ``obfuscated_blocks`` — list with ``placeholder`` and ``obfuscated_code``.

    Writes:
        - ``reassembled_html`` — list of ``{filename, content}`` dicts.
        - ``reassembled`` — new canonical key (same data).
    """

    def __init__(self) -> None:
        self._delegate = ReassembleContent()

    def call(self, payload: Payload) -> Payload:
        return self._delegate.call(payload)
