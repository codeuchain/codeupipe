"""Tests for ScanSkillDomains — delegates to test_agent_docs_pipeline.

This file exists to satisfy CUP002 (one test file per source file).
The actual tests run from test_agent_docs_pipeline.py; here we add a
minimal smoke test so this isn't an empty file.
"""

from codeupipe import Payload
from codeupipe.linter.scan_skill_domains import ScanSkillDomains
from codeupipe.testing import run_filter


def test_empty_directory_returns_no_domains(tmp_path):
    result = run_filter(ScanSkillDomains(), Payload({"directory": str(tmp_path)}))
    assert result.get("skill_domains") == []
