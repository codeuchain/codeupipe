"""Unit tests for SyncLocalSourcesLink.

Verifies that the link correctly:
- Passes through new capabilities (not in registry)
- Skips unchanged capabilities (same content_hash)
- Re-queues changed capabilities (different content_hash)
- Removes stale entries from registry
- Tracks sync stats accurately
- Passes through non-file capabilities (no source_path)
"""

import numpy as np
import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry
from codeupipe.ai.filters.registration.sync_local import SyncLocalSourcesLink


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def registry(tmp_path):
    """Create a fresh in-memory-like registry in a temp directory."""
    db_path = tmp_path / "test_sync.db"
    reg = CapabilityRegistry(db_path)
    yield reg
    reg.close()


def _dummy_embedding(dim: int = 1024) -> np.ndarray:
    """Create a dummy embedding for insertion."""
    return np.random.default_rng(42).random(dim).astype(np.float32)


def _make_cap(
    name: str,
    cap_type: CapabilityType = CapabilityType.SKILL,
    source_path: str = "",
    content_hash: str = "abc123",
) -> CapabilityDefinition:
    """Helper to create a CapabilityDefinition."""
    return CapabilityDefinition(
        name=name,
        description=f"Description of {name}",
        capability_type=cap_type,
        source_path=source_path,
        content_hash=content_hash,
    )


# ── Tests: New Capabilities ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_new_capability_passes_through(registry):
    """New capabilities (not in registry) should pass through for registration."""
    cap = _make_cap("new-skill", source_path="/skills/new/SKILL.md")

    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": [cap],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    to_register = result.get("scanned_capabilities")
    assert len(to_register) == 1
    assert to_register[0].name == "new-skill"


@pytest.mark.asyncio
async def test_new_capability_stats(registry):
    """Stats should show added=1 for new capability."""
    cap = _make_cap("new-skill", source_path="/skills/new/SKILL.md")

    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": [cap],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    stats = result.get("sync_stats")
    assert stats["added"] == 1
    assert stats["updated"] == 0
    assert stats["unchanged"] == 0
    assert stats["removed"] == 0


# ── Tests: Unchanged Capabilities ────────────────────────────────────


@pytest.mark.asyncio
async def test_unchanged_capability_skipped(registry):
    """Capabilities with same content_hash should be skipped."""
    # Pre-register in the registry
    cap = _make_cap("existing", source_path="/skills/ex/SKILL.md", content_hash="hash1")
    registry.insert(cap, _dummy_embedding())

    # Scan returns the same file with same hash
    scanned = _make_cap("existing-rescan", source_path="/skills/ex/SKILL.md", content_hash="hash1")

    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": [scanned],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    to_register = result.get("scanned_capabilities")
    assert len(to_register) == 0


@pytest.mark.asyncio
async def test_unchanged_capability_stats(registry):
    """Stats should show unchanged=1 for same-hash capability."""
    cap = _make_cap("existing", source_path="/skills/ex/SKILL.md", content_hash="hash1")
    registry.insert(cap, _dummy_embedding())

    scanned = _make_cap("existing", source_path="/skills/ex/SKILL.md", content_hash="hash1")

    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": [scanned],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    stats = result.get("sync_stats")
    assert stats["unchanged"] == 1
    assert stats["added"] == 0


# ── Tests: Changed Capabilities ──────────────────────────────────────


@pytest.mark.asyncio
async def test_changed_capability_re_queued(registry):
    """Capabilities with different content_hash should be re-queued."""
    old = _make_cap("my-skill", source_path="/skills/my/SKILL.md", content_hash="old_hash")
    registry.insert(old, _dummy_embedding())

    updated = _make_cap(
        "my-skill-v2",
        source_path="/skills/my/SKILL.md",
        content_hash="new_hash",
    )

    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": [updated],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    to_register = result.get("scanned_capabilities")
    assert len(to_register) == 1
    assert to_register[0].content_hash == "new_hash"


@pytest.mark.asyncio
async def test_changed_capability_old_deleted(registry):
    """Old entry should be deleted from registry when content changes."""
    old = _make_cap("my-skill", source_path="/skills/my/SKILL.md", content_hash="old_hash")
    registry.insert(old, _dummy_embedding())

    updated = _make_cap(
        "my-skill",
        source_path="/skills/my/SKILL.md",
        content_hash="new_hash",
    )

    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": [updated],
        "capability_registry": registry,
    })
    await link.call(ctx)

    # Old entry should be gone
    assert registry.get_by_source_path("/skills/my/SKILL.md") is None


@pytest.mark.asyncio
async def test_changed_capability_stats(registry):
    """Stats should show updated=1 for changed capability."""
    old = _make_cap("my-skill", source_path="/skills/my/SKILL.md", content_hash="old_hash")
    registry.insert(old, _dummy_embedding())

    updated = _make_cap(
        "my-skill",
        source_path="/skills/my/SKILL.md",
        content_hash="new_hash",
    )

    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": [updated],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    stats = result.get("sync_stats")
    assert stats["updated"] == 1


# ── Tests: Stale Removal ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stale_entries_removed(registry):
    """Registry entries not in scan results should be removed."""
    # Register a SKILL that no longer exists on disk
    stale = _make_cap(
        "deleted-skill",
        cap_type=CapabilityType.SKILL,
        source_path="/skills/gone/SKILL.md",
        content_hash="stale",
    )
    registry.insert(stale, _dummy_embedding())

    # Scan returns nothing for skills
    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": [],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    stats = result.get("sync_stats")
    assert stats["removed"] == 1
    assert registry.get_by_source_path("/skills/gone/SKILL.md") is None


@pytest.mark.asyncio
async def test_stale_removal_only_affects_local_types(registry):
    """Stale removal should not touch TOOL capabilities (from MCP servers)."""
    tool = _make_cap(
        "server-tool",
        cap_type=CapabilityType.TOOL,
        source_path="",
        content_hash="",
    )
    tool.server_name = "math-server"
    registry.insert(tool, _dummy_embedding())

    # Scan returns nothing — but tools should not be removed
    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": [],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    stats = result.get("sync_stats")
    assert stats["removed"] == 0
    assert registry.get_by_name("server-tool") is not None


# ── Tests: No source_path passthrough ────────────────────────────────


@pytest.mark.asyncio
async def test_no_source_path_passes_through(registry):
    """Capabilities without source_path should pass through directly."""
    cap = _make_cap("adhoc-cap", source_path="", content_hash="")

    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": [cap],
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    to_register = result.get("scanned_capabilities")
    assert len(to_register) == 1
    assert to_register[0].name == "adhoc-cap"


# ── Tests: Mixed scenario ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mixed_scenario(registry):
    """Test new + unchanged + changed + stale all at once."""
    # Pre-register: one unchanged, one changed, one stale
    unchanged = _make_cap(
        "stable", source_path="/skills/stable/SKILL.md", content_hash="same"
    )
    registry.insert(unchanged, _dummy_embedding())

    to_change = _make_cap(
        "evolving", source_path="/skills/evolving/SKILL.md", content_hash="v1"
    )
    registry.insert(to_change, _dummy_embedding())

    stale = _make_cap(
        "obsolete",
        cap_type=CapabilityType.INSTRUCTION,
        source_path="/prompts/obsolete.instructions.md",
        content_hash="old",
    )
    registry.insert(stale, _dummy_embedding())

    # Scanned: stable (unchanged), evolving (changed), brand-new
    scanned = [
        _make_cap("stable", source_path="/skills/stable/SKILL.md", content_hash="same"),
        _make_cap("evolving-v2", source_path="/skills/evolving/SKILL.md", content_hash="v2"),
        _make_cap(
            "fresh",
            cap_type=CapabilityType.PLAN,
            source_path="/docs/FRESH.md",
            content_hash="new",
        ),
    ]

    link = SyncLocalSourcesLink()
    ctx = Payload({
        "scanned_capabilities": scanned,
        "capability_registry": registry,
    })
    result = await link.call(ctx)

    to_register = result.get("scanned_capabilities")
    stats = result.get("sync_stats")

    assert len(to_register) == 2  # evolving-v2 + fresh
    names = {c.name for c in to_register}
    assert "evolving-v2" in names
    assert "fresh" in names

    assert stats["added"] == 1
    assert stats["updated"] == 1
    assert stats["unchanged"] == 1
    assert stats["removed"] == 1  # obsolete instruction


# ── Tests: Error handling ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_raises_without_scanned_capabilities(registry):
    """Should raise ValueError when scanned_capabilities is missing."""
    link = SyncLocalSourcesLink()
    ctx = Payload({"capability_registry": registry})

    with pytest.raises(ValueError, match="scanned_capabilities"):
        await link.call(ctx)


@pytest.mark.asyncio
async def test_raises_without_registry():
    """Should raise ValueError when capability_registry is missing."""
    link = SyncLocalSourcesLink()
    ctx = Payload({"scanned_capabilities": []})

    with pytest.raises(ValueError, match="capability_registry"):
        await link.call(ctx)
