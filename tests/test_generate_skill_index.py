"""Tests for GenerateSkillIndex — delegates to test_agent_docs_pipeline.

This file exists to satisfy CUP002 (one test file per source file).
"""

from codeupipe import Payload
from codeupipe.linter.generate_skill_index import GenerateSkillIndex
from codeupipe.testing import run_filter


def test_empty_domains_produces_valid_markdown():
    result = run_filter(GenerateSkillIndex(), Payload({
        "skill_domains": [],
        "site_url": "",
        "project_name": "test",
        "docs_dir": "docs",
    }))
    assert "# test — Agent Skill Index" in result.get("skill_index_content")
