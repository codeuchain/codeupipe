"""Tests for GenerateDomainDocs — delegates to test_agent_docs_pipeline.

This file exists to satisfy CUP002 (one test file per source file).
"""

from codeupipe import Payload
from codeupipe.linter.generate_domain_doc import GenerateDomainDocs
from codeupipe.testing import run_filter


def test_validate_mode_does_not_write(tmp_path):
    result = run_filter(GenerateDomainDocs(), Payload({
        "skill_domains": [
            {"name": "core", "summary": "Primitives", "exports": ["Payload"], "modules": ["pkg/core"]},
        ],
        "site_url": "",
        "project_name": "proj",
        "docs_dir": str(tmp_path / "docs"),
        "agent_docs_mode": "validate",
    }))
    assert "core" in result.get("domain_docs")
    assert result.get("domain_docs_written") == []
