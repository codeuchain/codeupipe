"""
LintPipeline: CUP standards linter — built with CUP itself (dogfooding).

Scans a directory and enforces CUP000–CUP008 rules:
  CUP000: Syntax error in file
  CUP001: Multiple components in one file
  CUP002: Missing test file
  CUP003: Filter missing call()
  CUP004: Tap missing observe()
  CUP005: StreamFilter missing stream()
  CUP006: Hook missing lifecycle methods
  CUP007: File name not snake_case
  CUP008: Stale __init__.py bundle
"""

from codeupipe import Pipeline, Payload

# TODO: update import paths to match your project layout
from .scan_directory import ScanDirectory
from .check_naming import CheckNaming
from .check_structure import CheckStructure
from .check_protocols import CheckProtocols
from .check_tests import CheckTests
from .check_bundle import CheckBundle


def build_lint_pipeline() -> Pipeline:
    """
    Construct the LintPipeline pipeline.

    Steps:
        1. ScanDirectory (Filter)
        2. CheckNaming (Filter)
        3. CheckStructure (Filter)
        4. CheckProtocols (Filter)
        5. CheckTests (Filter)
        6. CheckBundle (Filter)

    Use pipeline.run(payload) for single-payload execution.
    Use pipeline.stream(source) for streaming execution.
    """
    pipeline = Pipeline()

    pipeline.add_filter(ScanDirectory(), "scan_directory")
    pipeline.add_filter(CheckNaming(), "check_naming")
    pipeline.add_filter(CheckStructure(), "check_structure")
    pipeline.add_filter(CheckProtocols(), "check_protocols")
    pipeline.add_filter(CheckTests(), "check_tests")
    pipeline.add_filter(CheckBundle(), "check_bundle")

    return pipeline
