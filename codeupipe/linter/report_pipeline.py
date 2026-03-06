"""
ReportPipeline: Full codebase health report — built with CUP.

Composes coverage analysis, orphan detection, git history, and
report assembly into a single pipeline.

Reuses: ScanComponents, ScanTests, MapCoverage, ReportGaps
New:    DetectOrphans, GitHistory, AssembleReport
"""

from codeupipe import Pipeline

from .scan_components import ScanComponents
from .scan_tests import ScanTests
from .map_coverage import MapCoverage
from .report_gaps import ReportGaps
from .detect_orphans import DetectOrphans
from .git_history import GitHistory
from .assemble_report import AssembleReport


def build_report_pipeline() -> Pipeline:
    """
    Construct the full report pipeline.

    Steps:
        1. ScanComponents — catalog components + public methods
        2. ScanTests — parse test files, map tested symbols
        3. MapCoverage — cross-reference coverage
        4. ReportGaps — compute summary + gaps
        5. DetectOrphans — find unreferenced components/tests
        6. GitHistory — retrieve git log per file
        7. AssembleReport — merge into unified report

    Use pipeline.run(payload) with:
        - directory (str): component directory path
        - tests_dir (str, optional): test directory (default: "tests")
    """
    pipeline = Pipeline()

    pipeline.add_filter(ScanComponents(), "scan_components")
    pipeline.add_filter(ScanTests(), "scan_tests")
    pipeline.add_filter(MapCoverage(), "map_coverage")
    pipeline.add_filter(ReportGaps(), "report_gaps")
    pipeline.add_filter(DetectOrphans(), "detect_orphans")
    pipeline.add_filter(GitHistory(), "git_history")
    pipeline.add_filter(AssembleReport(), "assemble_report")

    return pipeline
