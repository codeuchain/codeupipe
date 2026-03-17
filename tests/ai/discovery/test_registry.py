"""Unit tests for the SQLite CapabilityRegistry."""

import numpy as np
import pytest

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType
from codeupipe.ai.discovery.registry import CapabilityRegistry


@pytest.fixture
def registry(tmp_path):
    """Create a fresh in-memory-like registry per test."""
    db = tmp_path / "test_registry.db"
    reg = CapabilityRegistry(db)
    yield reg
    reg.close()


@pytest.fixture
def sample_capability():
    """A reusable test capability."""
    return CapabilityDefinition(
        name="echo_message",
        description="Echoes a message back to the user",
        capability_type=CapabilityType.TOOL,
        server_name="echo-server",
        command="python -m echo",
        args_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        metadata={"version": 1},
    )


def _random_embedding(dims: int = 1024) -> np.ndarray:
    """Generate a normalised random embedding."""
    vec = np.random.randn(dims).astype(np.float32)
    return vec / np.linalg.norm(vec)


# ── Insert ────────────────────────────────────────────────────────────


class TestInsert:
    def test_insert_returns_id(self, registry, sample_capability):
        cap_id = registry.insert(sample_capability)
        assert isinstance(cap_id, int)
        assert cap_id > 0

    def test_insert_sets_id_on_capability(self, registry, sample_capability):
        registry.insert(sample_capability)
        assert sample_capability.id is not None

    def test_insert_with_embedding(self, registry, sample_capability):
        emb = _random_embedding()
        cap_id = registry.insert(sample_capability, embedding=emb)
        retrieved = registry.get(cap_id)
        assert retrieved is not None
        assert retrieved.embedding is not None

    def test_insert_duplicate_name_raises(self, registry, sample_capability):
        registry.insert(sample_capability)
        dup = CapabilityDefinition(name="echo_message", description="duplicate")
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            registry.insert(dup)


# ── Read ──────────────────────────────────────────────────────────────


class TestRead:
    def test_get_by_id(self, registry, sample_capability):
        cap_id = registry.insert(sample_capability)
        result = registry.get(cap_id)
        assert result is not None
        assert result.name == "echo_message"
        assert result.server_name == "echo-server"

    def test_get_nonexistent_returns_none(self, registry):
        assert registry.get(9999) is None

    def test_get_by_name(self, registry, sample_capability):
        registry.insert(sample_capability)
        result = registry.get_by_name("echo_message")
        assert result is not None
        assert result.description == "Echoes a message back to the user"

    def test_get_by_name_nonexistent(self, registry):
        assert registry.get_by_name("nonexistent") is None

    def test_list_all(self, registry):
        registry.insert(CapabilityDefinition(name="a", description="alpha"))
        registry.insert(CapabilityDefinition(name="b", description="beta"))
        registry.insert(CapabilityDefinition(name="c", description="gamma"))
        assert len(registry.list_all()) == 3

    def test_list_all_with_type_filter(self, registry):
        registry.insert(
            CapabilityDefinition(
                name="tool1", description="a tool", capability_type=CapabilityType.TOOL
            )
        )
        registry.insert(
            CapabilityDefinition(
                name="skill1", description="a skill", capability_type=CapabilityType.SKILL
            )
        )
        tools = registry.list_all(type_filter=CapabilityType.TOOL)
        assert len(tools) == 1
        assert tools[0].name == "tool1"

    def test_preserves_args_schema(self, registry, sample_capability):
        registry.insert(sample_capability)
        result = registry.get_by_name("echo_message")
        assert "properties" in result.args_schema
        assert "message" in result.args_schema["properties"]

    def test_preserves_metadata(self, registry, sample_capability):
        registry.insert(sample_capability)
        result = registry.get_by_name("echo_message")
        assert result.metadata == {"version": 1}


# ── Delete ────────────────────────────────────────────────────────────


class TestDelete:
    def test_delete_by_id(self, registry, sample_capability):
        cap_id = registry.insert(sample_capability)
        assert registry.delete(cap_id) is True
        assert registry.get(cap_id) is None

    def test_delete_nonexistent_returns_false(self, registry):
        assert registry.delete(9999) is False

    def test_delete_by_name(self, registry, sample_capability):
        registry.insert(sample_capability)
        assert registry.delete_by_name("echo_message") is True
        assert registry.get_by_name("echo_message") is None

    def test_delete_by_server(self, registry):
        registry.insert(
            CapabilityDefinition(name="a", description="x", server_name="srv1")
        )
        registry.insert(
            CapabilityDefinition(name="b", description="y", server_name="srv1")
        )
        registry.insert(
            CapabilityDefinition(name="c", description="z", server_name="srv2")
        )
        removed = registry.delete_by_server("srv1")
        assert removed == 2
        assert len(registry.list_all()) == 1


# ── Vector search ─────────────────────────────────────────────────────


class TestVectorSearch:
    def test_vector_search_returns_sorted(self, registry):
        """More similar embeddings should score higher."""
        target = _random_embedding()
        # Insert 3 capabilities with varying similarity
        similar = target + np.random.randn(1024).astype(np.float32) * 0.01
        similar /= np.linalg.norm(similar)
        dissimilar = _random_embedding()

        registry.insert(
            CapabilityDefinition(name="similar", description="close"),
            embedding=similar,
        )
        registry.insert(
            CapabilityDefinition(name="dissimilar", description="far"),
            embedding=dissimilar,
        )

        results = registry.vector_search(target, top_k=10)
        assert len(results) == 2
        # First result should be the more similar one
        top_id, top_score = results[0]
        assert registry.get(top_id).name == "similar"
        assert top_score > results[1][1]

    def test_vector_search_coarse(self, registry):
        """Coarse search uses only the first N dimensions."""
        emb = _random_embedding()
        registry.insert(
            CapabilityDefinition(name="cap1", description="test"),
            embedding=emb,
        )
        results = registry.vector_search(emb, top_k=5, use_coarse=True, coarse_dims=256)
        assert len(results) == 1
        assert results[0][1] > 0.9  # Self-similarity should be very high

    def test_vector_search_with_type_filter(self, registry):
        emb1 = _random_embedding()
        emb2 = _random_embedding()
        registry.insert(
            CapabilityDefinition(
                name="tool1", description="a tool", capability_type=CapabilityType.TOOL
            ),
            embedding=emb1,
        )
        registry.insert(
            CapabilityDefinition(
                name="skill1", description="a skill", capability_type=CapabilityType.SKILL
            ),
            embedding=emb2,
        )
        results = registry.vector_search(
            emb1, top_k=10, capability_type=CapabilityType.TOOL
        )
        assert len(results) == 1

    def test_vector_search_respects_top_k(self, registry):
        for i in range(10):
            registry.insert(
                CapabilityDefinition(name=f"cap_{i}", description=f"cap {i}"),
                embedding=_random_embedding(),
            )
        results = registry.vector_search(_random_embedding(), top_k=3)
        assert len(results) == 3

    def test_vector_search_empty_registry(self, registry):
        results = registry.vector_search(_random_embedding(), top_k=5)
        assert results == []


# ── Full-text search ──────────────────────────────────────────────────


class TestTextSearch:
    def test_fts_finds_by_name(self, registry):
        registry.insert(
            CapabilityDefinition(name="weather_forecast", description="gets weather")
        )
        registry.insert(
            CapabilityDefinition(name="calculator", description="does math")
        )
        results = registry.text_search("weather")
        assert len(results) == 1
        assert results[0].name == "weather_forecast"

    def test_fts_finds_by_description(self, registry):
        registry.insert(
            CapabilityDefinition(
                name="adder", description="adds two numbers together"
            )
        )
        results = registry.text_search("numbers")
        assert len(results) == 1

    def test_fts_with_type_filter(self, registry):
        registry.insert(
            CapabilityDefinition(
                name="math_tool",
                description="does math",
                capability_type=CapabilityType.TOOL,
            )
        )
        registry.insert(
            CapabilityDefinition(
                name="math_skill",
                description="does math",
                capability_type=CapabilityType.SKILL,
            )
        )
        results = registry.text_search("math", type_filter=CapabilityType.SKILL)
        assert len(results) == 1
        assert results[0].name == "math_skill"

    def test_fts_empty_result(self, registry):
        results = registry.text_search("nonexistent")
        assert results == []


# ── Context manager ───────────────────────────────────────────────────


class TestContextManager:
    def test_context_manager(self, tmp_path):
        db = tmp_path / "ctx.db"
        with CapabilityRegistry(db) as reg:
            reg.insert(CapabilityDefinition(name="x", description="y"))
            assert len(reg.list_all()) == 1
