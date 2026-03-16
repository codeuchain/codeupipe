"""
Source Protection — configurable build pipeline for obfuscating, minifying,
and protecting source files before deployment to public hosting.

Inspired by the ZTDC prototype's build.js pipeline. Generalizes the pattern
for any project that needs source protection — HTML, JS, CSS, and beyond.

Features:
    - **Preset profiles**: light, medium, heavy, paranoid
    - **Configurable file types**: scan any extension, extract any tag pattern
    - **Dead code injection**: syntactically valid noise to confuse reverse engineering
    - **Per-stage toggling**: enable/disable individual pipeline stages
    - **Config file loading**: JSON or TOML config files

Pipeline: scan → extract → [inject dead code] → transform → reassemble → minify → write output.
"""

from .obfuscate_config import (
    ObfuscateConfig,
    PRESETS,
    DEFAULT_FILE_TYPES,
    DEFAULT_STAGES,
    DEFAULT_JS_OBFUSCATOR_OPTS,
    DEFAULT_HTML_MINIFIER_OPTS,
    DEFAULT_RESERVED_NAMES,
    DEFAULT_RESERVED_STRINGS,
)
from .obfuscate_pipeline import build_obfuscate_pipeline

# ── New generic filter names ─────────────────────────────
from .scan_source_files import ScanSourceFiles
from .extract_embedded_code import ExtractEmbeddedCode
from .inject_dead_code import InjectDeadCode
from .transform_code import TransformCode
from .reassemble_content import ReassembleContent
from .minify_content import MinifyContent
from .write_output import WriteOutput

# ── Backward-compat aliases ─────────────────────────────
from .scan_html_files import ScanHtmlFiles
from .extract_inline_scripts import ExtractInlineScripts
from .obfuscate_scripts import ObfuscateScripts
from .reassemble_html import ReassembleHtml
from .minify_html import MinifyHtml

__all__ = [
    # Config
    "ObfuscateConfig",
    "PRESETS",
    "DEFAULT_FILE_TYPES",
    "DEFAULT_STAGES",
    "DEFAULT_JS_OBFUSCATOR_OPTS",
    "DEFAULT_HTML_MINIFIER_OPTS",
    "DEFAULT_RESERVED_NAMES",
    "DEFAULT_RESERVED_STRINGS",
    # Pipeline builder
    "build_obfuscate_pipeline",
    # New generic filters
    "ScanSourceFiles",
    "ExtractEmbeddedCode",
    "InjectDeadCode",
    "TransformCode",
    "ReassembleContent",
    "MinifyContent",
    "WriteOutput",
    # Backward-compat aliases
    "ScanHtmlFiles",
    "ExtractInlineScripts",
    "ObfuscateScripts",
    "ReassembleHtml",
    "MinifyHtml",
]
