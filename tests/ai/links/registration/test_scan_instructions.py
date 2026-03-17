"""Unit tests for ScanInstructionsLink.

Verifies that the link correctly:
- Finds *.instructions.md files in configured directories
- Extracts name from filename
- Extracts description from content
- Extracts applyTo from frontmatter
- Resolves relative paths against project_root
- Handles empty/missing directories gracefully
"""

import hashlib

import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityType
from codeupipe.ai.filters.registration.scan_instructions import ScanInstructionsLink


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def instr_dir(tmp_path):
    """Create a temp instructions directory with one .instructions.md."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    instr = prompts / "codestyle.instructions.md"
    instr.write_text(
        "---\n"
        "applyTo: '**/*.py'\n"
        "---\n\n"
        "# Code Style Rules\n\n"
        "Follow PEP 8.\n"
    )
    return tmp_path


@pytest.fixture
def instr_no_frontmatter(tmp_path):
    """Create an instructions file without frontmatter."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    instr = prompts / "testing.instructions.md"
    instr.write_text("# Testing Guidelines\n\nAlways write tests first.\n")
    return tmp_path


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_finds_instruction_files(instr_dir):
    """Should discover *.instructions.md files."""
    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [instr_dir / "prompts"],
        "project_root": instr_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 1
    assert caps[0].name == "codestyle"


@pytest.mark.asyncio
async def test_scan_sets_instruction_type(instr_dir):
    """Each capability should be typed as INSTRUCTION."""
    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [instr_dir / "prompts"],
        "project_root": instr_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].capability_type == CapabilityType.INSTRUCTION


@pytest.mark.asyncio
async def test_scan_extracts_description(instr_dir):
    """Should extract first heading as description."""
    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [instr_dir / "prompts"],
        "project_root": instr_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].description == "Code Style Rules"


@pytest.mark.asyncio
async def test_scan_extracts_applies_to(instr_dir):
    """Should extract applyTo from frontmatter into metadata."""
    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [instr_dir / "prompts"],
        "project_root": instr_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].metadata["applies_to"] == "**/*.py"


@pytest.mark.asyncio
async def test_scan_defaults_applies_to_star_star(instr_no_frontmatter):
    """Should default applyTo to ** when not in frontmatter."""
    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [instr_no_frontmatter / "prompts"],
        "project_root": instr_no_frontmatter,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].metadata["applies_to"] == "**"


@pytest.mark.asyncio
async def test_scan_sets_source_path(instr_dir):
    """Should record the full source_path."""
    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [instr_dir / "prompts"],
        "project_root": instr_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert "codestyle.instructions.md" in caps[0].source_path


@pytest.mark.asyncio
async def test_scan_computes_content_hash(instr_dir):
    """Should compute SHA-256 hash of file content."""
    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [instr_dir / "prompts"],
        "project_root": instr_dir,
    })
    result = await link.call(ctx)

    instr_file = instr_dir / "prompts" / "codestyle.instructions.md"
    expected_hash = hashlib.sha256(instr_file.read_text().encode()).hexdigest()

    caps = result.get("scanned_capabilities")
    assert caps[0].content_hash == expected_hash


@pytest.mark.asyncio
async def test_scan_resolves_relative_paths(instr_dir):
    """Should resolve relative paths against project_root."""
    link = ScanInstructionsLink()
    # Pass relative path — should be resolved against project_root
    ctx = Payload({
        "instructions_paths": ["prompts"],
        "project_root": instr_dir,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 1
    assert caps[0].name == "codestyle"


@pytest.mark.asyncio
async def test_scan_empty_directory(tmp_path):
    """Should return empty list when no instructions found."""
    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [tmp_path],
        "project_root": tmp_path,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps == []


@pytest.mark.asyncio
async def test_scan_missing_directory():
    """Should skip nonexistent directories."""
    from pathlib import Path

    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [Path("/nonexistent/instr/path")],
        "project_root": Path("/nonexistent"),
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps == []


@pytest.mark.asyncio
async def test_scan_multiple_instructions(tmp_path):
    """Should find all *.instructions.md files."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    for name in ["auth", "logging", "security"]:
        (prompts / f"{name}.instructions.md").write_text(f"# {name.title()} Rules\n")

    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [prompts],
        "project_root": tmp_path,
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 3
    names = {c.name for c in caps}
    assert names == {"auth", "logging", "security"}


@pytest.mark.asyncio
async def test_scan_appends_to_existing(instr_dir):
    """Should append to existing scanned_capabilities."""
    from codeupipe.ai.discovery.models import CapabilityDefinition

    existing = CapabilityDefinition(name="pre-existing", description="already here")
    link = ScanInstructionsLink()
    ctx = Payload({
        "instructions_paths": [instr_dir / "prompts"],
        "project_root": instr_dir,
        "scanned_capabilities": [existing],
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 2
    assert caps[0].name == "pre-existing"
    assert caps[1].name == "codestyle"


@pytest.mark.asyncio
async def test_scan_name_strips_instructions_suffix():
    """Name extraction should strip .instructions.md suffix."""
    link = ScanInstructionsLink()
    from pathlib import Path

    name = link._extract_name(Path("some/dir/my-rules.instructions.md"))
    assert name == "my-rules"
