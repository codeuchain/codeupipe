"""
doc_check_pipeline: Wires the doc-code sync check pipeline.

Scans markdown for cup:ref markers, resolves file references,
checks symbol existence, detects hash drift, validates index
coverage, and assembles a report.
"""

from codeupipe import Pipeline

from .scan_docs import ScanDocs
from .resolve_refs import ResolveRefs
from .check_symbols import CheckSymbols
from .detect_drift import DetectDrift
from .check_index import CheckIndex
from .assemble_doc_report import AssembleDocReport


def build_doc_check_pipeline() -> Pipeline:
    """Build and return the doc-check pipeline."""
    pipeline = Pipeline()
    pipeline.add_filter(ScanDocs(), "scan_docs")
    pipeline.add_filter(ResolveRefs(), "resolve_refs")
    pipeline.add_filter(CheckSymbols(), "check_symbols")
    pipeline.add_filter(DetectDrift(), "detect_drift")
    pipeline.add_filter(CheckIndex(), "check_index")
    pipeline.add_filter(AssembleDocReport(), "assemble_doc_report")
    return pipeline
