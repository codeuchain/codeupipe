"""Tests for the agent-docs pipeline and its four filters.

Covers:
- ScanSkillDomains (auto-discovery + config-driven)
- GenerateSkillIndex (template rendering)
- GenerateDomainDocs (init/update/validate modes, generated marker)
- ValidateAgentDocs (completeness checks)
- build_agent_docs_pipeline (full integration)
"""

import textwrap

import pytest

from codeupipe import Payload
from codeupipe.testing import run_filter, run_pipeline, assert_keys

from codeupipe.linter.scan_skill_domains import ScanSkillDomains
from codeupipe.linter.generate_skill_index import GenerateSkillIndex
from codeupipe.linter.generate_domain_doc import GenerateDomainDocs
from codeupipe.linter.validate_agent_docs import ValidateAgentDocs
from codeupipe.linter.agent_docs_pipeline import build_agent_docs_pipeline


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def fake_project(tmp_path):
    """Create a minimal project with two sub-packages and one top-level module."""
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        '"""mypkg root."""\n__all__ = ["Payload", "Filter"]\n',
        encoding="utf-8",
    )

    # Sub-package: core
    core = pkg / "core"
    core.mkdir()
    (core / "__init__.py").write_text(
        '"""Core primitives for pipelines."""\n__all__ = ["Payload", "Filter", "Pipeline"]\n',
        encoding="utf-8",
    )

    # Sub-package: utils
    utils = pkg / "utils"
    utils.mkdir()
    (utils / "__init__.py").write_text(
        '"""Utility helpers."""\n__all__ = ["retry"]\n',
        encoding="utf-8",
    )

    # Top-level module: testing.py
    (pkg / "testing.py").write_text(
        '"""Test helpers for mypkg."""\n__all__ = ["run_filter", "assert_payload"]\n',
        encoding="utf-8",
    )

    # Should be ignored
    (pkg / "__pycache__").mkdir()
    (pkg / "_private").mkdir()
    (pkg / "_private" / "__init__.py").write_text("", encoding="utf-8")

    return tmp_path


@pytest.fixture()
def fake_docs(tmp_path):
    """Create docs/agents/ with two hand-maintained docs."""
    docs = tmp_path / "docs"
    docs.mkdir()
    agents = docs / "agents"
    agents.mkdir()

    # Index
    (docs / "agents.md").write_text(
        "# Skill Index\n\n/agents/core.txt\n/agents/utils.txt\n",
        encoding="utf-8",
    )

    # Hand-maintained core doc (no generated marker)
    (agents / "core.md").write_text(
        "# Core\n\n> `curl https://example.io/agents/core.txt`\n",
        encoding="utf-8",
    )

    # Generated utils doc (has marker)
    (agents / "utils.md").write_text(
        "<!-- agent-docs:generated -->\n# Utils\n\n> `curl https://example.io/agents/utils.txt`\n",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture()
def nav_file(tmp_path):
    """Create a minimal mkdocs.yml with agent doc nav entries."""
    content = textwrap.dedent("""\
        nav:
          - Home: index.md
          - Agent Docs:
            - Skill Index: agents.md
            - Core: agents/core.md
            - Utils: agents/utils.md
    """)
    path = tmp_path / "mkdocs.yml"
    path.write_text(content, encoding="utf-8")
    return path


# ── ScanSkillDomains ────────────────────────────────────────────────


class TestScanSkillDomains:
    """Tests for the ScanSkillDomains filter."""

    def test_auto_discovers_subpackages(self, fake_project):
        payload = Payload({"directory": str(fake_project)})
        result = run_filter(ScanSkillDomains(), payload)
        domains = result.get("skill_domains")
        names = [d["name"] for d in domains]
        assert "core" in names
        assert "utils" in names

    def test_auto_discovers_top_level_modules(self, fake_project):
        payload = Payload({"directory": str(fake_project)})
        result = run_filter(ScanSkillDomains(), payload)
        domains = result.get("skill_domains")
        names = [d["name"] for d in domains]
        assert "testing" in names

    def test_reads_exports_from_all(self, fake_project):
        payload = Payload({"directory": str(fake_project)})
        result = run_filter(ScanSkillDomains(), payload)
        domains = result.get("skill_domains")
        core = next(d for d in domains if d["name"] == "core")
        assert "Payload" in core["exports"]
        assert "Filter" in core["exports"]
        assert "Pipeline" in core["exports"]
        assert core["export_count"] == 3

    def test_ignores_private_and_pycache(self, fake_project):
        payload = Payload({"directory": str(fake_project)})
        result = run_filter(ScanSkillDomains(), payload)
        names = [d["name"] for d in result.get("skill_domains")]
        assert "__pycache__" not in names
        assert "_private" not in names

    def test_extracts_module_docstring(self, fake_project):
        payload = Payload({"directory": str(fake_project)})
        result = run_filter(ScanSkillDomains(), payload)
        domains = result.get("skill_domains")
        core = next(d for d in domains if d["name"] == "core")
        assert "Core primitives" in core["summary"]

    def test_config_driven_domains(self, fake_project):
        config = {
            "domains": [
                {
                    "name": "core",
                    "summary": "Pipeline primitives",
                    "modules": ["mypkg/core"],
                },
            ],
        }
        payload = Payload({
            "directory": str(fake_project),
            "agent_docs_config": config,
        })
        result = run_filter(ScanSkillDomains(), payload)
        domains = result.get("skill_domains")
        assert len(domains) == 1
        assert domains[0]["name"] == "core"
        assert "Payload" in domains[0]["exports"]

    def test_config_with_project_name(self, fake_project):
        payload = Payload({
            "directory": str(fake_project),
            "agent_docs_config": {"project_name": "mypkg"},
        })
        result = run_filter(ScanSkillDomains(), payload)
        names = [d["name"] for d in result.get("skill_domains")]
        assert "core" in names

    def test_empty_directory(self, tmp_path):
        payload = Payload({"directory": str(tmp_path)})
        result = run_filter(ScanSkillDomains(), payload)
        assert result.get("skill_domains") == []

    def test_no_all_still_returns_empty_exports(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text('"""Root."""\n', encoding="utf-8")
        sub = pkg / "empty_mod"
        sub.mkdir()
        (sub / "__init__.py").write_text('"""No exports."""\n', encoding="utf-8")

        payload = Payload({"directory": str(tmp_path)})
        result = run_filter(ScanSkillDomains(), payload)
        domains = result.get("skill_domains")
        mod = next((d for d in domains if d["name"] == "empty_mod"), None)
        assert mod is not None
        assert mod["exports"] == []
        assert mod["export_count"] == 0


# ── GenerateSkillIndex ──────────────────────────────────────────────


class TestGenerateSkillIndex:
    """Tests for the GenerateSkillIndex filter."""

    def test_generates_markdown_content(self):
        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Pipeline primitives", "exports": ["Payload"], "modules": []},
                {"name": "utils", "summary": "Helpers", "exports": ["retry"], "modules": []},
            ],
            "site_url": "https://example.io/proj",
            "project_name": "myproject",
            "docs_dir": "docs",
        })
        result = run_filter(GenerateSkillIndex(), payload)
        content = result.get("skill_index_content")
        assert "# myproject — Agent Skill Index" in content
        assert "/agents/core.txt" in content
        assert "/agents/utils.txt" in content
        assert "https://example.io/proj" in content

    def test_sets_index_path(self):
        payload = Payload({
            "skill_domains": [],
            "site_url": "",
            "project_name": "test",
            "docs_dir": "mydocs",
        })
        result = run_filter(GenerateSkillIndex(), payload)
        assert result.get("skill_index_path") == "mydocs/agents.md"

    def test_skill_rows_contain_all_domains(self):
        domains = [
            {"name": "core", "summary": "Primitives", "exports": [], "modules": []},
            {"name": "browser", "summary": "Browser tools", "exports": [], "modules": []},
            {"name": "auth", "summary": "Authentication", "exports": [], "modules": []},
        ]
        payload = Payload({
            "skill_domains": domains,
            "site_url": "https://x.io",
            "project_name": "p",
            "docs_dir": "docs",
        })
        result = run_filter(GenerateSkillIndex(), payload)
        content = result.get("skill_index_content")
        assert "**Core**" in content
        assert "**Browser**" in content
        assert "**Auth**" in content

    def test_empty_domains_produces_valid_markdown(self):
        payload = Payload({
            "skill_domains": [],
            "site_url": "",
            "project_name": "empty",
            "docs_dir": "docs",
        })
        result = run_filter(GenerateSkillIndex(), payload)
        content = result.get("skill_index_content")
        assert "# empty — Agent Skill Index" in content


# ── GenerateDomainDocs ──────────────────────────────────────────────


class TestGenerateDomainDocs:
    """Tests for the GenerateDomainDocs filter."""

    def test_validate_mode_does_not_write(self, tmp_path):
        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Primitives", "exports": ["Payload"], "modules": ["pkg/core"]},
            ],
            "site_url": "https://x.io",
            "project_name": "proj",
            "docs_dir": str(tmp_path / "docs"),
            "agent_docs_mode": "validate",
        })
        result = run_filter(GenerateDomainDocs(), payload)
        assert "core" in result.get("domain_docs")
        assert result.get("domain_docs_written") == []
        assert not (tmp_path / "docs" / "agents" / "core.md").exists()

    def test_init_mode_creates_files(self, tmp_path):
        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Primitives", "exports": ["Payload"], "modules": ["pkg/core"]},
            ],
            "site_url": "https://x.io",
            "project_name": "proj",
            "docs_dir": str(tmp_path / "docs"),
            "agent_docs_mode": "init",
        })
        result = run_filter(GenerateDomainDocs(), payload)
        written = result.get("domain_docs_written")
        assert len(written) == 1
        content = (tmp_path / "docs" / "agents" / "core.md").read_text(encoding="utf-8")
        assert "<!-- agent-docs:generated -->" in content
        assert "proj Core" in content

    def test_init_mode_does_not_overwrite_existing(self, tmp_path):
        docs = tmp_path / "docs" / "agents"
        docs.mkdir(parents=True)
        existing = docs / "core.md"
        existing.write_text("Hand-maintained content", encoding="utf-8")

        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Primitives", "exports": [], "modules": []},
            ],
            "site_url": "",
            "project_name": "proj",
            "docs_dir": str(tmp_path / "docs"),
            "agent_docs_mode": "init",
        })
        result = run_filter(GenerateDomainDocs(), payload)
        assert result.get("domain_docs_written") == []
        assert existing.read_text(encoding="utf-8") == "Hand-maintained content"

    def test_update_mode_overwrites_generated(self, tmp_path):
        docs = tmp_path / "docs" / "agents"
        docs.mkdir(parents=True)
        target = docs / "core.md"
        target.write_text(
            "<!-- agent-docs:generated -->\n# Old generated content",
            encoding="utf-8",
        )

        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Primitives", "exports": ["Payload"], "modules": ["pkg/core"]},
            ],
            "site_url": "https://x.io",
            "project_name": "proj",
            "docs_dir": str(tmp_path / "docs"),
            "agent_docs_mode": "update",
        })
        result = run_filter(GenerateDomainDocs(), payload)
        written = result.get("domain_docs_written")
        assert str(target) in written
        content = target.read_text(encoding="utf-8")
        assert "proj Core" in content

    def test_update_mode_preserves_hand_maintained(self, tmp_path):
        docs = tmp_path / "docs" / "agents"
        docs.mkdir(parents=True)
        target = docs / "core.md"
        target.write_text("# Hand-written Core docs\n\nCareful work here.", encoding="utf-8")

        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Primitives", "exports": [], "modules": []},
            ],
            "site_url": "",
            "project_name": "proj",
            "docs_dir": str(tmp_path / "docs"),
            "agent_docs_mode": "update",
        })
        result = run_filter(GenerateDomainDocs(), payload)
        assert result.get("domain_docs_written") == []
        assert target.read_text(encoding="utf-8") == "# Hand-written Core docs\n\nCareful work here."

    def test_generated_content_has_curl_url(self, tmp_path):
        payload = Payload({
            "skill_domains": [
                {"name": "auth", "summary": "Auth", "exports": ["login"], "modules": ["pkg/auth"]},
            ],
            "site_url": "https://my.site",
            "project_name": "proj",
            "docs_dir": str(tmp_path / "docs"),
            "agent_docs_mode": "init",
        })
        result = run_filter(GenerateDomainDocs(), payload)
        content = result.get("domain_docs")["auth"]
        assert "curl https://my.site/agents/auth.txt" in content

    def test_export_table_lists_all_exports(self, tmp_path):
        payload = Payload({
            "skill_domains": [
                {
                    "name": "core",
                    "summary": "Primitives",
                    "exports": ["Payload", "Filter", "Pipeline"],
                    "modules": ["pkg/core"],
                },
            ],
            "site_url": "",
            "project_name": "proj",
            "docs_dir": str(tmp_path / "docs"),
            "agent_docs_mode": "validate",
        })
        result = run_filter(GenerateDomainDocs(), payload)
        content = result.get("domain_docs")["core"]
        assert "`Payload`" in content
        assert "`Filter`" in content
        assert "`Pipeline`" in content


# ── ValidateAgentDocs ───────────────────────────────────────────────


class TestValidateAgentDocs:
    """Tests for the ValidateAgentDocs filter."""

    def test_all_present_status_ok(self, fake_docs, nav_file):
        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Primitives", "exports": []},
                {"name": "utils", "summary": "Helpers", "exports": []},
            ],
            "docs_dir": str(fake_docs / "docs"),
            "nav_file": str(nav_file),
        })
        result = run_filter(ValidateAgentDocs(), payload)
        report = result.get("agent_docs_report")
        assert report["status"] == "ok"
        assert report["total_domains"] == 2
        assert report["documented"] == 2
        assert report["missing"] == []
        assert report["orphaned"] == []

    def test_missing_domain_doc_reported(self, fake_docs, nav_file):
        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Primitives", "exports": []},
                {"name": "utils", "summary": "Helpers", "exports": []},
                {"name": "browser", "summary": "Browser", "exports": []},
            ],
            "docs_dir": str(fake_docs / "docs"),
            "nav_file": str(nav_file),
        })
        result = run_filter(ValidateAgentDocs(), payload)
        report = result.get("agent_docs_report")
        assert report["status"] == "issues_found"
        assert "browser" in report["missing"]
        assert report["documented"] == 2

    def test_orphaned_doc_reported(self, fake_docs, nav_file):
        # Create an extra doc not in domains
        (fake_docs / "docs" / "agents" / "legacy.md").write_text(
            "# Legacy\n\n> `curl x/agents/legacy.txt`\n", encoding="utf-8",
        )
        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Primitives", "exports": []},
                {"name": "utils", "summary": "Helpers", "exports": []},
            ],
            "docs_dir": str(fake_docs / "docs"),
            "nav_file": str(nav_file),
        })
        result = run_filter(ValidateAgentDocs(), payload)
        report = result.get("agent_docs_report")
        assert "legacy" in report["orphaned"]

    def test_missing_index_reported(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        payload = Payload({
            "skill_domains": [],
            "docs_dir": str(docs),
            "nav_file": str(tmp_path / "mkdocs.yml"),
        })
        result = run_filter(ValidateAgentDocs(), payload)
        report = result.get("agent_docs_report")
        issues = report["issues"]
        assert any(i["type"] == "missing_index" for i in issues)

    def test_missing_curl_url_reported(self, tmp_path):
        docs = tmp_path / "docs"
        agents = docs / "agents"
        agents.mkdir(parents=True)
        (docs / "agents.md").write_text("# Index\n/agents/core.txt\n", encoding="utf-8")
        # core.md without the curl URL
        (agents / "core.md").write_text("# Core\n\nNo curl URL here.\n", encoding="utf-8")

        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Primitives", "exports": []},
            ],
            "docs_dir": str(docs),
            "nav_file": str(tmp_path / "missing.yml"),
        })
        result = run_filter(ValidateAgentDocs(), payload)
        report = result.get("agent_docs_report")
        assert any(i["type"] == "missing_curl_url" for i in report["issues"])

    def test_missing_nav_entries_reported(self, fake_docs, tmp_path):
        # Nav file without agent docs
        nav = tmp_path / "mkdocs.yml"
        nav.write_text("nav:\n  - Home: index.md\n", encoding="utf-8")

        payload = Payload({
            "skill_domains": [
                {"name": "core", "summary": "Primitives", "exports": []},
            ],
            "docs_dir": str(fake_docs / "docs"),
            "nav_file": str(nav),
        })
        result = run_filter(ValidateAgentDocs(), payload)
        report = result.get("agent_docs_report")
        assert any(i["type"] == "missing_nav_index" for i in report["issues"])
        assert any(i["type"] == "missing_nav_domain" for i in report["issues"])


# ── Pipeline Integration ────────────────────────────────────────────


class TestAgentDocsPipeline:
    """Integration tests for the full agent-docs pipeline."""

    def test_pipeline_runs_validate_mode(self, fake_project):
        """Validate mode: scans project, checks existing docs."""
        # Set up docs inside the same project dir
        docs_dst = fake_project / "docs"
        docs_dst.mkdir(exist_ok=True)
        agents_dst = docs_dst / "agents"
        agents_dst.mkdir(exist_ok=True)

        (docs_dst / "agents.md").write_text(
            "# Skill Index\n\n/agents/core.txt\n/agents/utils.txt\n/agents/testing.txt\n",
            encoding="utf-8",
        )
        (agents_dst / "core.md").write_text(
            "# Core\n\n> `curl https://example.io/agents/core.txt`\n",
            encoding="utf-8",
        )
        (agents_dst / "utils.md").write_text(
            "<!-- agent-docs:generated -->\n# Utils\n\n> `curl https://example.io/agents/utils.txt`\n",
            encoding="utf-8",
        )
        (agents_dst / "testing.md").write_text(
            "<!-- agent-docs:generated -->\n# Testing\n\n> `curl https://example.io/agents/testing.txt`\n",
            encoding="utf-8",
        )

        nav = fake_project / "mkdocs.yml"
        nav.write_text(
            "nav:\n  - agents.md\n  - agents/core.md\n  - agents/utils.md\n  - agents/testing.md\n",
            encoding="utf-8",
        )

        pipeline = build_agent_docs_pipeline()
        result = run_pipeline(pipeline, {
            "directory": str(fake_project),
            "agent_docs_mode": "validate",
            "site_url": "https://example.io",
            "project_name": "mypkg",
            "docs_dir": str(docs_dst),
            "nav_file": str(nav),
            "agent_docs_config": {},
        })
        assert_keys(result, "skill_domains", "skill_index_content", "domain_docs", "agent_docs_report")
        report = result.get("agent_docs_report")
        assert report["total_domains"] > 0

    def test_pipeline_init_creates_docs(self, fake_project):
        """Init mode: creates agents.md + domain docs from scratch."""
        docs_dir = fake_project / "docs"
        docs_dir.mkdir(exist_ok=True)

        pipeline = build_agent_docs_pipeline()
        result = run_pipeline(pipeline, {
            "directory": str(fake_project),
            "agent_docs_mode": "init",
            "site_url": "https://example.io/proj",
            "project_name": "mypkg",
            "docs_dir": str(docs_dir),
            "nav_file": str(fake_project / "mkdocs.yml"),
            "agent_docs_config": {},
        })

        # Verify files were written
        written = result.get("domain_docs_written")
        assert len(written) > 0

        # Verify index was generated
        index_content = result.get("skill_index_content")
        assert "mypkg — Agent Skill Index" in index_content

        # Verify domain docs exist on disk
        for path in written:
            from pathlib import Path
            assert Path(path).exists()

    def test_pipeline_update_preserves_hand_maintained(self, fake_project):
        """Update mode: overwrites generated files, preserves hand-maintained."""
        docs_dst = fake_project / "docs"
        docs_dst.mkdir(exist_ok=True)
        agents_dst = docs_dst / "agents"
        agents_dst.mkdir(exist_ok=True)

        (docs_dst / "agents.md").write_text(
            "# Skill Index\n\n/agents/core.txt\n/agents/utils.txt\n",
            encoding="utf-8",
        )
        # Hand-maintained core doc (no generated marker)
        (agents_dst / "core.md").write_text(
            "# Core\n\n> `curl https://example.io/agents/core.txt`\n",
            encoding="utf-8",
        )
        # Generated utils doc (has marker)
        (agents_dst / "utils.md").write_text(
            "<!-- agent-docs:generated -->\n# Utils\n\n> `curl https://example.io/agents/utils.txt`\n",
            encoding="utf-8",
        )

        pipeline = build_agent_docs_pipeline()
        result = run_pipeline(pipeline, {
            "directory": str(fake_project),
            "agent_docs_mode": "update",
            "site_url": "https://example.io",
            "project_name": "mypkg",
            "docs_dir": str(docs_dst),
            "nav_file": str(fake_project / "mkdocs.yml"),
            "agent_docs_config": {},
        })

        written = result.get("domain_docs_written")
        written_names = [p.split("/")[-1] for p in written]

        # utils.md had generated marker → should be overwritten
        assert "utils.md" in written_names

        # core.md was hand-maintained → should NOT be overwritten
        assert "core.md" not in written_names

        # Verify hand-maintained content preserved
        core_content = (docs_dst / "agents" / "core.md").read_text(encoding="utf-8")
        assert "# Core" in core_content
        assert "<!-- agent-docs:generated -->" not in core_content
