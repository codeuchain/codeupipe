"""ScanHtmlFiles — backward-compat alias for ScanSourceFiles."""

from codeupipe import Payload
from .scan_source_files import ScanSourceFiles


class ScanHtmlFiles:
    """Scan src_dir for HTML files to process.

    .. deprecated::
        Use :class:`ScanSourceFiles` instead. This class delegates to it
        and ensures ``html_sources`` is always written for backward compat.

    Reads:
        - ``config`` — ObfuscateConfig dict with ``src_dir``, ``html_files``.

    Writes:
        - ``html_sources`` — list of ``{filename, path, content, size}`` dicts.
        - ``sources`` — same data (new canonical key).
    """

    def __init__(self) -> None:
        self._delegate = ScanSourceFiles()

    def call(self, payload: Payload) -> Payload:
        # Ensure file_types defaults to HTML if not specified
        config = payload.get("config") or {}
        if "file_types" not in config:
            config = dict(config)
            config["file_types"] = [{"extensions": [".html"]}]
            payload = payload.insert("config", config)
        return self._delegate.call(payload)
