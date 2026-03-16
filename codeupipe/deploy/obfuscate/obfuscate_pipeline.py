"""
Source protection pipeline builder — dynamic composition based on config.

Usage::

    from codeupipe import Pipeline, Payload
    from codeupipe.deploy.obfuscate import build_obfuscate_pipeline, ObfuscateConfig

    config = ObfuscateConfig(src_dir="src/", out_dir="dist/", preset="heavy")
    pipeline = build_obfuscate_pipeline(config=config)
    result = asyncio.run(pipeline.run(Payload({"config": config.to_dict()})))
"""

from typing import Optional

from codeupipe import Pipeline

from .obfuscate_config import ObfuscateConfig
from .scan_source_files import ScanSourceFiles
from .extract_embedded_code import ExtractEmbeddedCode
from .inject_dead_code import InjectDeadCode
from .transform_code import TransformCode
from .reassemble_content import ReassembleContent
from .minify_content import MinifyContent
from .write_output import WriteOutput


def build_obfuscate_pipeline(
    config: Optional[ObfuscateConfig] = None,
    *,
    strict: bool = False,
) -> Pipeline:
    """Build the source protection pipeline.

    Dynamically composes pipeline stages based on ``config.stages`` and
    ``config.dead_code``.  When no config is provided, builds the classic
    6-stage pipeline for full backward compatibility.

    Pipeline stages (when all enabled):
        1. ScanSourceFiles     — discover files by extension
        2. ExtractEmbeddedCode — regex-extract inline code blocks
        3. InjectDeadCode      — (optional) insert non-functional code
        4. TransformCode       — shell out to obfuscator tool
        5. ReassembleContent   — inject processed code back into templates
        6. MinifyContent       — shell out to minifier tool
        7. WriteOutput         — write files + copy static assets

    Args:
        config: ObfuscateConfig instance. If None, uses classic 6-stage pipeline.
        strict: If True, raise when JS/HTML tools are not installed.

    Returns:
        Pipeline ready to run with ``Payload({"config": config_dict})``.
    """
    pipeline = Pipeline()

    if config is None:
        # Classic backward-compat pipeline — 6 stages, no dead code
        pipeline.add_filter(ScanSourceFiles(), "scan_source_files")
        pipeline.add_filter(ExtractEmbeddedCode(), "extract_embedded_code")
        pipeline.add_filter(TransformCode(strict=strict), "transform_code")
        pipeline.add_filter(ReassembleContent(), "reassemble_content")
        pipeline.add_filter(MinifyContent(strict=strict), "minify_content")
        pipeline.add_filter(WriteOutput(), "write_output")
        return pipeline

    stages = config.stages
    dead_code = config.dead_code

    if stages.get("scan", True):
        pipeline.add_filter(ScanSourceFiles(), "scan_source_files")

    if stages.get("extract", True):
        pipeline.add_filter(ExtractEmbeddedCode(), "extract_embedded_code")

    # Dead code injection — only if enabled AND extract stage is on
    if dead_code.get("enabled", False) and stages.get("extract", True):
        pipeline.add_filter(InjectDeadCode(), "inject_dead_code")

    if stages.get("transform", True):
        pipeline.add_filter(TransformCode(strict=strict), "transform_code")

    if stages.get("reassemble", True):
        pipeline.add_filter(ReassembleContent(), "reassemble_content")

    if stages.get("minify", True):
        pipeline.add_filter(MinifyContent(strict=strict), "minify_content")

    if stages.get("write", True):
        pipeline.add_filter(WriteOutput(), "write_output")

    return pipeline
