"""Unit tests for ScanPlansLink.

Verifies that the link correctly:
- Finds *.md files in configured plan directories
- Extracts name from filename
- Extracts description from first heading
- Hashes content with SHA-256
- Creates CapabilityDefinition entries with PLAN type
- Resolves relative paths against project_root
- Handles empty/missing directories gracefully
"""

import hashlib

import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityType
from codeupipe.ai.filters.registration.scan_plans import ScanPlansLink


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def plans_dir(tmp_path):
    """Create a temp docs directory with one plan .md file."""
    docs = tmp_path / "docs"
    docs.mkdir()
    plan = docs / "MIGRATION_PLAN.md"
    plan.write_text(
        "# Database Migration Plan\n\n"
        "## Phase 1\n\n"
        "Migrate users table.\n"
    )
    return tmp_path


@pytest.fixture
def plans_dir_no_heading(tmp_path):
    """Create a plan file without any heading."""
    docs = tmp_path / "docs"
    docs.mkdir()
    plan = docs / "notes.md"
    plan.write_text("Just some loose notes here.\nNo heading at all.\n")
    return tmp_path


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_finds_plan_files(plans_dir):
    """Should discover .md files in plan directories."""
    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [plans_dir / "docs"],
        "project_root": plans_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 1
    assert caps[0].name == "MIGRATION_PLAN"


@pytest.mark.asyncio
async def test_scan_sets_plan_type(plans_dir):
    """Each capability should be typed as PLAN."""
    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [plans_dir / "docs"],
        "project_root": plans_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].capability_type == CapabilityType.PLAN


@pytest.mark.asyncio
async def test_scan_extracts_heading_as_description(plans_dir):
    """Should extract first heading as description."""
    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [plans_dir / "docs"],
        "project_root": plans_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].description == "Database Migration Plan"


@pytest.mark.asyncio
async def test_scan_empty_description_no_heading(plans_dir_no_heading):
    """Should return empty description when no heading found."""
    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [plans_dir_no_heading / "docs"],
        "project_root": plans_dir_no_heading,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].description == ""


@pytest.mark.asyncio
async def test_scan_sets_source_path(plans_dir):
    """Should record the full source_path of the .md file."""
    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [plans_dir / "docs"],
        "project_root": plans_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert "MIGRATION_PLAN.md" in caps[0].source_path


@pytest.mark.asyncio
async def test_scan_computes_content_hash(plans_dir):
    """Should compute SHA-256 hash of file content."""
    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [plans_dir / "docs"],
        "project_root": plans_dir,
    })
    result = await link.call(ctx)

    plan_file = plans_dir / "docs" / "MIGRATION_PLAN.md"
    expected_hash = hashlib.sha256(plan_file.read_text().encode()).hexdigest()

    caps = result.get("scanned_capabilities")
    assert caps[0].content_hash == expected_hash


@pytest.mark.asyncio
async def test_scan_resolves_relative_paths(plans_dir):
    """Should resolve relative paths against project_root."""
    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": ["docs"],
        "project_root": plans_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 1
    assert caps[0].name == "MIGRATION_PLAN"


@pytest.mark.asyncio
async def test_scan_empty_directory(tmp_path):
    """Should return empty list when no .md files found."""
    empty = tmp_path / "empty"
    empty.mkdir()
    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [empty],
        "project_root": tmp_path,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps == []


@pytest.mark.asyncio
async def test_scan_missing_directory():
    """Should skip nonexistent directories."""
    from pathlib import Path

    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [Path("/nonexistent/docs/path")],
        "project_root": Path("/nonexistent"),
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps == []


@pytest.mark.asyncio
async def test_scan_multiple_plans(tmp_path):
    """Should find all .md files across the directory."""
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in ["ROADMAP", "ALIGNMENT", "ARCHITECTURE"]:
        (docs / f"{name}.md").write_text(f"# {name.title()} Plan\n")

    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [docs],
        "project_root": tmp_path,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 3
    names = {c.name for c in caps}
    assert names == {"ROADMAP", "ALIGNMENT", "ARCHITECTURE"}


@pytest.mark.asyncio
async def test_scan_nested_plans(tmp_path):
    """Should find .md files in nested subdirectories."""
    docs = tmp_path / "docs"
    sub = docs / "sprints" / "sprint-1"
    sub.mkdir(parents=True)
    (sub / "retro.md").write_text("# Sprint 1 Retro\n")

    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [docs],
        "project_root": tmp_path,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 1
    assert caps[0].name == "retro"


@pytest.mark.asyncio
async def test_scan_appends_to_existing(plans_dir):
    """Should append to existing scanned_capabilities."""
    from codeupipe.ai.discovery.models import CapabilityDefinition

    existing = CapabilityDefinition(name="pre-existing", description="already here")
    link = ScanPlansLink()
    ctx = Payload({
        "plans_paths": [plans_dir / "docs"],
        "project_root": plans_dir,
        "scanned_capabilities": [existing],
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 2
    assert caps[0].name == "pre-existing"
    assert caps[1].name == "MIGRATION_PLAN"


@pytest.mark.asyncio
async def test_scan_name_from_filename():
    """Name extraction should use stem (no extension)."""
    link = ScanPlansLink()
    from pathlib import Path

    name = link._extract_name(Path("/some/path/my-plan.md"))
    assert name == "my-plan"
