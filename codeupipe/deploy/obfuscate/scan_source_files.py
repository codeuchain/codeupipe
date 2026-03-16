"""ScanSourceFiles — discover source files by configurable extensions."""

import os
from typing import List

from codeupipe import Payload


class ScanSourceFiles:
    """Scan src_dir for files matching configured file type extensions.

    Generalizes ScanHtmlFiles to support any file type via config.file_types.

    Reads:
        - ``config`` — dict with ``src_dir``, ``html_files`` (explicit list),
          ``file_types`` (list of dicts with ``extensions``).

    Writes:
        - ``sources`` — list of ``{filename, path, content, size}`` dicts.
        - ``html_sources`` — backward-compat alias (same data).
    """

    def call(self, payload: Payload) -> Payload:
        config = payload.get("config") or {}
        src_dir = config.get("src_dir", "")
        explicit_files = config.get("html_files")
        file_types = config.get("file_types") or [{"extensions": [".html"]}]

        if not src_dir or not os.path.isdir(src_dir):
            raise FileNotFoundError(f"Source directory not found: {src_dir!r}")

        # Collect all configured extensions
        all_extensions = set()
        for ft in file_types:
            for ext in ft.get("extensions", []):
                all_extensions.add(ext.lower())

        sources: List[dict] = []

        if explicit_files:
            filenames = explicit_files
        else:
            # Auto-detect files matching any configured extension
            filenames = sorted(
                f for f in os.listdir(src_dir)
                if any(f.lower().endswith(ext) for ext in all_extensions)
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

        return (
            payload
            .insert("sources", sources)
            .insert("html_sources", sources)  # backward compat
        )
