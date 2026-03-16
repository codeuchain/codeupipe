"""WriteOutput — write built HTML files and copy static assets to output directory."""

import os
import shutil
from typing import List

from codeupipe import Payload


class WriteOutput:
    """Write minified HTML and copy static assets to the output directory.

    Reads:
        - ``minified_html`` — list of ``{filename, content, ...}`` dicts.
        - ``config`` — dict with ``src_dir``, ``out_dir``, ``static_copy``.

    Writes:
        - ``build_results`` — list of ``{filename, path, size}`` for written files.
        - ``static_copied`` — list of static asset names copied.
    """

    def call(self, payload: Payload) -> Payload:
        html_list = (
            payload.get("minified")
            or payload.get("minified_html")
            or []
        )
        config = payload.get("config") or {}
        src_dir = config.get("src_dir", "")
        out_dir = config.get("out_dir", "")
        static_copy = config.get("static_copy", [])

        if not out_dir:
            raise ValueError("config.out_dir is required")

        os.makedirs(out_dir, exist_ok=True)

        # Write HTML files
        build_results: List[dict] = []
        for item in html_list:
            out_path = os.path.join(out_dir, item["filename"])
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(item["content"])
            size = len(item["content"].encode("utf-8"))
            build_results.append({
                "filename": item["filename"],
                "path": out_path,
                "size": size,
            })

        # Copy static assets
        copied: List[str] = []
        for name in static_copy:
            src_path = os.path.join(src_dir, name)
            # Try src/ first, fall back to out_dir (already at root)
            if not os.path.exists(src_path):
                src_path = os.path.join(out_dir, name)
            dest_path = os.path.join(out_dir, name)

            if src_path == dest_path:
                if os.path.exists(dest_path):
                    copied.append(name)
                continue
            if not os.path.exists(src_path):
                continue

            if os.path.isdir(src_path):
                if os.path.exists(dest_path):
                    shutil.rmtree(dest_path)
                shutil.copytree(src_path, dest_path)
            else:
                shutil.copy2(src_path, dest_path)
            copied.append(name)

        return (
            payload
            .insert("build_results", build_results)
            .insert("static_copied", copied)
        )
