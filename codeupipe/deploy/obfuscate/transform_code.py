"""TransformCode — pluggable code transformation per file type (replaces ObfuscateScripts)."""

import json
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List

from codeupipe import Payload


class TransformCode:
    """Transform extracted code blocks using configurable tools.

    Generalizes ObfuscateScripts to support pluggable tools per file type.
    Currently supports javascript-obfuscator; architecture allows future tools.

    Reads:
        - ``code_blocks`` (or ``script_blocks``) — list from ExtractEmbeddedCode.
        - ``config`` — dict with ``js_opts``, ``reserved_names``, ``reserved_strings``.

    Writes:
        - ``transformed_blocks`` — list with ``transformed_code`` added.
        - ``transform_stats`` — dict with counts.
        - ``obfuscated_blocks`` — backward-compat alias.
        - ``obfuscate_stats`` — backward-compat alias.
    """

    def __init__(self, *, strict: bool = False):
        self._strict = strict

    def call(self, payload: Payload) -> Payload:
        blocks = payload.get("code_blocks") or payload.get("script_blocks") or []
        config = payload.get("config") or {}

        js_opts = config.get("js_opts", {})
        reserved_names = config.get("reserved_names", [])
        reserved_strings = config.get("reserved_strings", [])

        tool = _find_obfuscator()
        if not tool and self._strict:
            raise RuntimeError(
                "javascript-obfuscator not found. "
                "Install with: npm install -g javascript-obfuscator"
            )

        results: List[dict] = []
        stats = {"total": len(blocks), "transformed": 0, "skipped": 0, "errors": 0}

        for block in blocks:
            entry = dict(block)
            if tool:
                try:
                    transformed = _obfuscate_one(
                        block["code"], tool, js_opts,
                        reserved_names, reserved_strings,
                    )
                    entry["transformed_code"] = transformed
                    entry["obfuscated_code"] = transformed  # backward compat
                    stats["transformed"] += 1
                except Exception:
                    entry["transformed_code"] = block["code"]
                    entry["obfuscated_code"] = block["code"]
                    stats["errors"] += 1
            else:
                entry["transformed_code"] = block["code"]
                entry["obfuscated_code"] = block["code"]
                stats["skipped"] += 1

            results.append(entry)

        # Also produce backward-compat stats
        compat_stats = {
            "total": stats["total"],
            "obfuscated": stats["transformed"],
            "skipped": stats["skipped"],
            "errors": stats["errors"],
        }

        return (
            payload
            .insert("transformed_blocks", results)
            .insert("transform_stats", stats)
            .insert("obfuscated_blocks", results)     # backward compat
            .insert("obfuscate_stats", compat_stats)   # backward compat
        )


def _find_obfuscator() -> str:
    """Find javascript-obfuscator binary."""
    path = shutil.which("javascript-obfuscator")
    if path:
        return path
    npx = shutil.which("npx")
    if npx:
        return f"{npx} javascript-obfuscator"
    return ""


def _obfuscate_one(
    code: str,
    tool: str,
    opts: Dict[str, Any],
    reserved_names: List[str],
    reserved_strings: List[str],
) -> str:
    """Obfuscate a single JS code string."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as tmp_in:
        tmp_in.write(code)
        tmp_in_path = tmp_in.name

    tmp_out_path = tmp_in_path.replace(".js", "-obfuscated.js")

    try:
        cmd = _build_command(tool, tmp_in_path, tmp_out_path, opts,
                             reserved_names, reserved_strings)
        subprocess.run(
            cmd, shell=True, check=True, capture_output=True, timeout=120,
        )
        with open(tmp_out_path, "r", encoding="utf-8") as f:
            return f.read()
    finally:
        for p in (tmp_in_path, tmp_out_path):
            if os.path.exists(p):
                os.unlink(p)


def _build_command(
    tool: str,
    input_path: str,
    output_path: str,
    opts: Dict[str, Any],
    reserved_names: List[str],
    reserved_strings: List[str],
) -> str:
    """Build the CLI command string for javascript-obfuscator."""
    parts = [tool, input_path, "--output", output_path]

    for key, value in opts.items():
        flag = f"--{key}"
        if isinstance(value, bool):
            if value:
                parts.append(flag)
        elif isinstance(value, list):
            parts.extend([flag, json.dumps(value)])
        else:
            parts.extend([flag, str(value)])

    if reserved_names:
        parts.extend(["--reserved-names", " ".join(reserved_names)])
    if reserved_strings:
        parts.extend(["--reserved-strings", " ".join(reserved_strings)])

    return " ".join(parts)
