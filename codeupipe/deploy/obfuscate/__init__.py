"""
SPA Obfuscation — build pipeline for minifying HTML and obfuscating inline JavaScript.

Inspired by the ZTDC prototype's build.js pipeline. Generalizes the pattern
for any SPA that needs source protection before deployment to public hosting.

Pipeline: scan → extract scripts → obfuscate JS → reassemble → minify HTML → write output.
"""

from .obfuscate_config import (
    ObfuscateConfig,
    DEFAULT_JS_OBFUSCATOR_OPTS,
    DEFAULT_HTML_MINIFIER_OPTS,
    DEFAULT_RESERVED_NAMES,
    DEFAULT_RESERVED_STRINGS,
)
from .obfuscate_pipeline import build_obfuscate_pipeline
from .scan_html_files import ScanHtmlFiles
from .extract_inline_scripts import ExtractInlineScripts
from .obfuscate_scripts import ObfuscateScripts
from .reassemble_html import ReassembleHtml
from .minify_html import MinifyHtml
from .write_output import WriteOutput

__all__ = [
    "ObfuscateConfig",
    "build_obfuscate_pipeline",
    "ScanHtmlFiles",
    "ExtractInlineScripts",
    "ObfuscateScripts",
    "ReassembleHtml",
    "MinifyHtml",
    "WriteOutput",
    "DEFAULT_JS_OBFUSCATOR_OPTS",
    "DEFAULT_HTML_MINIFIER_OPTS",
    "DEFAULT_RESERVED_NAMES",
    "DEFAULT_RESERVED_STRINGS",
]
