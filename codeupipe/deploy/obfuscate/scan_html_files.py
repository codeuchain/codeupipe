"""ScanHtmlFiles — discover HTML files in the source directory."""

import os
from typing import List

from codeupipe import Payload


class ScanHtmlFiles:
    """Scan src_dir for HTML files to process.

    Reads:
        - ``config`` — ObfuscateConfig dict with ``src_dir``, ``html_files``.

    Writes:
        - ``html_sources`` — list of ``{filename, path, content, size}`` dicts.
    """

    def call(self, payload: Payload) -> Payload:
        config = payload.get("config") or {}
        src_dir = config.get("src_dir", "")
        explicit_files = config.get("html_files")

        if not src_dir or not os.path.isdir(src_dir):
            raise FileNotFoundError(f"Source directory not found: {src_dir!r}")

        sources: List[dict] = []

        if explicit_files:
            # Use explicit file list
            filenames = explicit_files
        else:
            # Auto-detect *.html files
            filenames = sorted(
                f for f in os.listdir(src_dir)
                if f.endswith(".html")
            )

        for fname in filenames:
            fpath = os.path.join(src_dir, fname)
            if not os.path.isfile(fpath):
                continue
            content = open(fpath, "r", encoding="utf-8").read()
            sources.append({
                "filename": fname,
                "path": fpath,
                "content": content,
                "size": len(content.encode("utf-8")),
            })

        return payload.insert("html_sources", sources)
