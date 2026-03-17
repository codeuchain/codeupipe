"""Tests for ValidateAgentDocs — delegates to test_agent_docs_pipeline.

This file exists to satisfy CUP002 (one test file per source file).
"""

from codeupipe import Payload
from codeupipe.linter.validate_agent_docs import ValidateAgentDocs
from codeupipe.testing import run_filter


def test_missing_index_reported(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    result = run_filter(ValidateAgentDocs(), Payload({
        "skill_domains": [],
        "docs_dir": str(docs),
        "nav_file": str(tmp_path / "mkdocs.yml"),
    }))
    report = result.get("agent_docs_report")
    assert any(i["type"] == "missing_index" for i in report["issues"])
