"""ObfuscateScripts — backward-compat alias for TransformCode."""

from codeupipe import Payload
from .transform_code import TransformCode


class ObfuscateScripts:
    """Obfuscate extracted inline script blocks using javascript-obfuscator.

    .. deprecated::
        Use :class:`TransformCode` instead. This class delegates to it
        and ensures ``obfuscated_blocks`` / ``obfuscate_stats`` are written.

    Reads:
        - ``script_blocks`` — list from ExtractInlineScripts.
        - ``config`` — dict with ``js_opts``, ``reserved_names``, ``reserved_strings``.

    Writes:
        - ``obfuscated_blocks`` — list with ``obfuscated_code`` added.
        - ``obfuscate_stats`` — dict with counts.
        - ``transformed_blocks`` — new canonical key (same data).
        - ``transform_stats`` — new canonical key (same data).
    """

    def __init__(self, *, strict: bool = False):
        self._delegate = TransformCode(strict=strict)

    def call(self, payload: Payload) -> Payload:
        # Ensure code_blocks exists from script_blocks
        if not payload.get("code_blocks") and payload.get("script_blocks"):
            payload = payload.insert("code_blocks", payload.get("script_blocks"))
        return self._delegate.call(payload)
