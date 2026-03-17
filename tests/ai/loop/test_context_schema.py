"""Tests for context_schema — Zone enum & ContextEntry dataclass.

RED → GREEN: Isolation tests for the schema types that will
underpin context positioning, budgeting, and pruning.
"""

import pytest

from codeupipe.ai.loop.context_schema import (
    ContextEntry,
    Zone,
    get_importance,
    SOURCE_IMPORTANCE,
)


# ── Zone enum ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestZone:
    """Zone enum — positioning zones for context entries."""

    def test_three_zones_exist(self):
        assert len(Zone) == 3

    def test_zone_ordering(self):
        """FOUNDATIONAL < CONTEXTUAL < FOCAL for sort-by-position."""
        assert Zone.FOUNDATIONAL < Zone.CONTEXTUAL < Zone.FOCAL

    def test_zone_values(self):
        assert Zone.FOUNDATIONAL == 0
        assert Zone.CONTEXTUAL == 1
        assert Zone.FOCAL == 2

    def test_zone_names(self):
        assert Zone.FOUNDATIONAL.name == "FOUNDATIONAL"
        assert Zone.CONTEXTUAL.name == "CONTEXTUAL"
        assert Zone.FOCAL.name == "FOCAL"

    def test_zone_is_int_enum(self):
        """Zones are comparable as ints for sorting."""
        zones = [Zone.FOCAL, Zone.FOUNDATIONAL, Zone.CONTEXTUAL]
        assert sorted(zones) == [
            Zone.FOUNDATIONAL,
            Zone.CONTEXTUAL,
            Zone.FOCAL,
        ]


# ── ContextEntry dataclass ────────────────────────────────────────────


@pytest.mark.unit
class TestContextEntry:
    """ContextEntry — immutable, typed context window entry."""

    def test_create_basic_entry(self):
        entry = ContextEntry(
            zone=Zone.FOCAL,
            source="user_prompt",
            content="build auth system",
        )
        assert entry.zone == Zone.FOCAL
        assert entry.source == "user_prompt"
        assert entry.content == "build auth system"

    def test_defaults(self):
        entry = ContextEntry(
            zone=Zone.CONTEXTUAL,
            source="history",
            content="some text",
        )
        assert entry.importance == 0.5
        assert entry.turn_added == 0
        assert entry.version == 1
        assert entry.metadata == {}

    def test_auto_token_estimate(self):
        """Token estimate auto-calculated from content if not provided."""
        content = "a" * 100  # 100 chars ÷ 4 = 25 tokens
        entry = ContextEntry(
            zone=Zone.CONTEXTUAL,
            source="test",
            content=content,
        )
        assert entry.token_estimate == 25

    def test_explicit_token_estimate(self):
        """Explicit token_estimate is preserved, not overwritten."""
        entry = ContextEntry(
            zone=Zone.CONTEXTUAL,
            source="test",
            content="hello",
            token_estimate=999,
        )
        assert entry.token_estimate == 999

    def test_empty_content_no_estimate(self):
        """Empty content → 0 token estimate (no auto-calc)."""
        entry = ContextEntry(
            zone=Zone.CONTEXTUAL,
            source="test",
            content="",
        )
        assert entry.token_estimate == 0

    def test_frozen_immutable(self):
        """ContextEntry is frozen — cannot reassign fields."""
        entry = ContextEntry(
            zone=Zone.FOUNDATIONAL,
            source="directive",
            content="be concise",
        )
        with pytest.raises(AttributeError):
            entry.content = "something else"

    def test_custom_importance(self):
        entry = ContextEntry(
            zone=Zone.FOUNDATIONAL,
            source="directive",
            content="be concise",
            importance=1.0,
        )
        assert entry.importance == 1.0

    def test_metadata(self):
        entry = ContextEntry(
            zone=Zone.CONTEXTUAL,
            source="tool_result",
            content="file contents",
            metadata={"tool": "read_file", "path": "/foo.py"},
        )
        assert entry.metadata["tool"] == "read_file"

    def test_to_dict(self):
        entry = ContextEntry(
            zone=Zone.FOCAL,
            source="user_prompt",
            content="test",
            importance=0.9,
            turn_added=3,
        )
        d = entry.to_dict()
        assert d["zone"] == "FOCAL"
        assert d["source"] == "user_prompt"
        assert d["content"] == "test"
        assert d["importance"] == 0.9
        assert d["turn_added"] == 3
        assert d["version"] == 1
        assert isinstance(d["token_estimate"], int)

    def test_sortable_by_zone(self):
        """Entries can be sorted by zone for positional ordering."""
        entries = [
            ContextEntry(zone=Zone.FOCAL, source="a", content="end"),
            ContextEntry(zone=Zone.FOUNDATIONAL, source="b", content="start"),
            ContextEntry(zone=Zone.CONTEXTUAL, source="c", content="mid"),
        ]
        sorted_entries = sorted(entries, key=lambda e: e.zone)
        assert [e.zone for e in sorted_entries] == [
            Zone.FOUNDATIONAL,
            Zone.CONTEXTUAL,
            Zone.FOCAL,
        ]

    def test_sortable_by_importance(self):
        """Within same zone, sort by importance descending."""
        entries = [
            ContextEntry(zone=Zone.CONTEXTUAL, source="a", content="lo", importance=0.3),
            ContextEntry(zone=Zone.CONTEXTUAL, source="b", content="hi", importance=0.9),
            ContextEntry(zone=Zone.CONTEXTUAL, source="c", content="md", importance=0.5),
        ]
        sorted_entries = sorted(
            entries,
            key=lambda e: (-e.importance,),
        )
        assert [e.importance for e in sorted_entries] == [0.9, 0.5, 0.3]

    def test_equality(self):
        """Frozen dataclass supports value-based equality."""
        a = ContextEntry(zone=Zone.FOCAL, source="x", content="y")
        b = ContextEntry(zone=Zone.FOCAL, source="x", content="y")
        assert a == b

    def test_hashable(self):
        """Frozen + no mutable defaults → NOT hashable due to dict metadata.
        But we can test that entries with custom metadata aren't hashable."""
        entry = ContextEntry(zone=Zone.FOCAL, source="x", content="y")
        # Default metadata={} — dict is unhashable so frozen dataclass
        # with mutable default_factory won't be hashable
        with pytest.raises(TypeError):
            hash(entry)


# ── Importance helpers ────────────────────────────────────────────────


@pytest.mark.unit
class TestImportanceHelpers:
    """Source importance lookup defaults."""

    def test_directive_highest(self):
        assert get_importance("directive") == 1.0

    def test_system_prompt_high(self):
        assert get_importance("system_prompt") == 0.95

    def test_notification_low(self):
        assert get_importance("notification") == 0.4

    def test_unknown_source_default(self):
        assert get_importance("unknown_source_xyz") == 0.5

    def test_all_sources_covered(self):
        """Every entry in SOURCE_IMPORTANCE has 0.0–1.0 range."""
        for source, imp in SOURCE_IMPORTANCE.items():
            assert 0.0 <= imp <= 1.0, f"{source} importance {imp} out of range"
