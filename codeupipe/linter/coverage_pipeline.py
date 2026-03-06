"""
CoveragePipeline: AST-based component coverage mapping — built with CUP.

Scans a component directory and its tests to produce:
  - Per-component method coverage map
  - Untested method gaps
  - Aggregate coverage summary
"""

from codeupipe import Pipeline, Payload

# TODO: update import paths to match your project layout
from .scan_components import ScanComponents
from .scan_tests import ScanTests
from .map_coverage import MapCoverage
from .report_gaps import ReportGaps


def build_coverage_pipeline() -> Pipeline:
    """
    Construct the CoveragePipeline pipeline.

    Steps:
        1. ScanComponents (Filter)
        2. ScanTests (Filter)
        3. MapCoverage (Filter)
        4. ReportGaps (Filter)

    Use pipeline.run(payload) for single-payload execution.
    Use pipeline.stream(source) for streaming execution.
    """
    pipeline = Pipeline()

    pipeline.add_filter(ScanComponents(), "scan_components")
    pipeline.add_filter(ScanTests(), "scan_tests")
    pipeline.add_filter(MapCoverage(), "map_coverage")
    pipeline.add_filter(ReportGaps(), "report_gaps")

    return pipeline
