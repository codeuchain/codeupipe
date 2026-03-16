"""
SPA obfuscation pipeline builder — compose filters into a complete build pipeline.

Usage::

    from codeupipe import Pipeline, Payload
    from codeupipe.deploy.obfuscate import build_obfuscate_pipeline, ObfuscateConfig

    config = ObfuscateConfig(src_dir="src/", out_dir="dist/")
    pipeline = build_obfuscate_pipeline()
    result = asyncio.run(pipeline.run(Payload({"config": config.to_dict()})))
"""

from codeupipe import Pipeline

from .scan_html_files import ScanHtmlFiles
from .extract_inline_scripts import ExtractInlineScripts
from .obfuscate_scripts import ObfuscateScripts
from .reassemble_html import ReassembleHtml
from .minify_html import MinifyHtml
from .write_output import WriteOutput


def build_obfuscate_pipeline(*, strict: bool = False) -> Pipeline:
    """Build the SPA obfuscation pipeline.

    Pipeline stages:
        1. ScanHtmlFiles     — discover HTML in src_dir
        2. ExtractInlineScripts — regex-extract <script> blocks
        3. ObfuscateScripts  — shell out to javascript-obfuscator
        4. ReassembleHtml    — inject obfuscated code back into templates
        5. MinifyHtml        — shell out to html-minifier-terser
        6. WriteOutput       — write files + copy static assets

    Args:
        strict: If True, raise when JS/HTML tools are not installed.
                If False (default), fall back to pass-through / lightweight.

    Returns:
        Pipeline ready to run with ``Payload({"config": config_dict})``.
    """
    pipeline = Pipeline()

    pipeline.add_filter(ScanHtmlFiles(), "scan_html_files")
    pipeline.add_filter(ExtractInlineScripts(), "extract_inline_scripts")
    pipeline.add_filter(ObfuscateScripts(strict=strict), "obfuscate_scripts")
    pipeline.add_filter(ReassembleHtml(), "reassemble_html")
    pipeline.add_filter(MinifyHtml(strict=strict), "minify_html")
    pipeline.add_filter(WriteOutput(), "write_output")

    return pipeline
