"""MinifyContent — pluggable content minification per file type (replaces MinifyHtml)."""

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List

from codeupipe import Payload


class MinifyContent:
    """Minify content after code blocks have been re-injected.

    Generalizes MinifyHtml to support pluggable minifiers per file type.
    Currently supports html-minifier-terser; falls back to whitespace-only
    compression if the tool is not available and ``strict=False``.

    Reads:
        - ``reassembled`` (or ``reassembled_html``) — list of ``{filename, content}`` dicts.
        - ``config`` — dict with ``html_opts``.

    Writes:
        - ``minified`` — list of ``{filename, content, original_size, minified_size}`` dicts.
        - ``minify_stats`` — dict with totals.
        - ``minified_html`` — backward-compat alias.
    """

    def __init__(self, *, strict: bool = False):
        self._strict = strict

    def call(self, payload: Payload) -> Payload:
        html_list = (
            payload.get("reassembled")
            or payload.get("reassembled_html")
            or []
        )
        config = payload.get("config") or {}
        html_opts = config.get("html_opts", {})

        tool = _find_minifier()
        if not tool and self._strict:
            raise RuntimeError(
                "html-minifier-terser not found. "
                "Install with: npm install -g html-minifier-terser"
            )

        results: List[dict] = []
        total_original = 0
        total_minified = 0

        for item in html_list:
            filename = item["filename"]
            content = item["content"]
            orig_size = len(content.encode("utf-8"))
            total_original += orig_size

            if tool:
                try:
                    minified = _minify_one(content, tool, html_opts)
                except Exception:
                    minified = content
            else:
                minified = _fallback_minify(content)

            min_size = len(minified.encode("utf-8"))
            total_minified += min_size

            results.append({
                "filename": filename,
                "content": minified,
                "original_size": orig_size,
                "minified_size": min_size,
            })

        stats = {
            "total_original": total_original,
            "total_minified": total_minified,
            "ratio": round(total_minified / total_original * 100, 1) if total_original else 0,
        }

        return (
            payload
            .insert("minified", results)
            .insert("minify_stats", stats)
            .insert("minified_html", results)  # backward compat
        )


def _find_minifier() -> str:
    """Find html-minifier-terser binary."""
    path = shutil.which("html-minifier-terser")
    if path:
        return path
    npx = shutil.which("npx")
    if npx:
        return f"{npx} html-minifier-terser"
    return ""


def _minify_one(content: str, tool: str, opts: Dict[str, Any]) -> str:
    """Minify a single HTML string."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        cmd_parts = [tool, tmp_path]
        for key, value in opts.items():
            flag = f"--{key}"
            if isinstance(value, bool):
                if value:
                    cmd_parts.append(flag)
            else:
                cmd_parts.extend([flag, str(value)])

        result = subprocess.run(
            " ".join(cmd_parts),
            shell=True, capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
        return content
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _fallback_minify(content: str) -> str:
    """Lightweight fallback: collapse whitespace, strip HTML comments.

    NOT a real minifier — just enough to reduce size when tools unavailable.
    """
    # Remove HTML comments (but not conditional/IE comments)
    content = re.sub(r"<!--(?!\[).*?-->", "", content, flags=re.DOTALL)
    # Collapse runs of whitespace
    content = re.sub(r"\s+", " ", content)
    # Remove spaces around tags
    content = re.sub(r">\s+<", "><", content)
    return content.strip()
