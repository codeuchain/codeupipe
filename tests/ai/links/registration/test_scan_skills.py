"""Unit tests for ScanSkillsLink.

Verifies that the link correctly:
- Finds SKILL.md files in configured directories
- Extracts name from frontmatter or directory name
- Extracts description from frontmatter or first paragraph
- Hashes content with SHA-256
- Creates CapabilityDefinition entries with SKILL type
- Handles empty/missing directories gracefully
"""

import hashlib

import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityType
from codeupipe.ai.filters.registration.scan_skills import ScanSkillsLink


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def skill_dir(tmp_path):
    """Create a temp skills directory with one SKILL.md."""
    skill = tmp_path / "my-skill"
    skill.mkdir()
    skill_md = skill / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: my-skill\n"
        "description: A test skill\n"
        "---\n\n"
        "# My Skill\n\n"
        "This skill does stuff.\n"
    )
    return tmp_path


@pytest.fixture
def skill_dir_no_frontmatter(tmp_path):
    """Create a SKILL.md without frontmatter name/description."""
    skill = tmp_path / "fallback-dir"
    skill.mkdir()
    skill_md = skill / "SKILL.md"
    skill_md.write_text("# Just a Heading\n\nSome body text here.\n")
    return tmp_path


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_finds_skill_files(skill_dir):
    """Should discover SKILL.md files and create capabilities."""
    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [skill_dir]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 1
    assert caps[0].name == "my-skill"


@pytest.mark.asyncio
async def test_scan_sets_skill_type(skill_dir):
    """Each capability should be typed as SKILL."""
    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [skill_dir]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].capability_type == CapabilityType.SKILL


@pytest.mark.asyncio
async def test_scan_extracts_description_from_frontmatter(skill_dir):
    """Should extract description from frontmatter."""
    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [skill_dir]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].description == "A test skill"


@pytest.mark.asyncio
async def test_scan_sets_source_path(skill_dir):
    """Should record the full source_path of the SKILL.md file."""
    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [skill_dir]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].source_path.endswith("SKILL.md")
    assert "my-skill" in caps[0].source_path


@pytest.mark.asyncio
async def test_scan_computes_content_hash(skill_dir):
    """Should compute SHA-256 hash of file content."""
    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [skill_dir]})
    result = await link.call(ctx)

    skill_file = skill_dir / "my-skill" / "SKILL.md"
    expected_hash = hashlib.sha256(skill_file.read_text().encode()).hexdigest()

    caps = result.get("scanned_capabilities")
    assert caps[0].content_hash == expected_hash


@pytest.mark.asyncio
async def test_scan_stores_skill_dir_in_metadata(skill_dir):
    """Should store the parent directory in metadata."""
    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [skill_dir]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert "skill_dir" in caps[0].metadata
    assert "my-skill" in caps[0].metadata["skill_dir"]


@pytest.mark.asyncio
async def test_scan_falls_back_to_dir_name(skill_dir_no_frontmatter):
    """Should use directory name when frontmatter has no name."""
    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [skill_dir_no_frontmatter]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].name == "fallback-dir"


@pytest.mark.asyncio
async def test_scan_falls_back_description_to_body(skill_dir_no_frontmatter):
    """Should use first non-heading body text when no frontmatter description."""
    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [skill_dir_no_frontmatter]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert "Some body text" in caps[0].description


@pytest.mark.asyncio
async def test_scan_empty_directory(tmp_path):
    """Should return empty list when no SKILL.md found."""
    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [tmp_path]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps == []


@pytest.mark.asyncio
async def test_scan_missing_directory():
    """Should skip nonexistent directories."""
    from pathlib import Path

    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [Path("/nonexistent/path/12345")]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps == []


@pytest.mark.asyncio
async def test_scan_multiple_skills(tmp_path):
    """Should find all SKILL.md files across subdirectories."""
    for name in ["alpha", "beta", "gamma"]:
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name} desc\n---\n")

    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [tmp_path]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 3
    names = {c.name for c in caps}
    assert names == {"alpha", "beta", "gamma"}


@pytest.mark.asyncio
async def test_scan_appends_to_existing(skill_dir):
    """Should append to existing scanned_capabilities, not overwrite."""
    from codeupipe.ai.discovery.models import CapabilityDefinition

    existing = CapabilityDefinition(name="pre-existing", description="already here")
    link = ScanSkillsLink()
    ctx = Payload({"skills_paths": [skill_dir], "scanned_capabilities": [existing]})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 2
    assert caps[0].name == "pre-existing"
    assert caps[1].name == "my-skill"
