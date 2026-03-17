"""Unit tests for the Settings configuration."""

import pytest

from codeupipe.ai.config import Settings, get_settings, reset_settings


@pytest.fixture(autouse=True)
def _reset():
    reset_settings()
    yield
    reset_settings()


class TestSettings:
    def test_default_values(self):
        s = Settings()
        assert s.coarse_search_dims == 256
        assert s.coarse_search_top_k == 50
        assert s.fine_search_top_k == 5
        assert s.process_timeout == 30.0
        assert "snowflake" in s.embedding_model.lower()

    def test_registry_path_resolved(self):
        s = Settings()
        assert s.registry_path.is_absolute()

    def test_immutable(self):
        s = Settings()
        with pytest.raises(Exception):
            s.coarse_search_dims = 512

    def test_coarse_dims_max(self):
        with pytest.raises(Exception):
            Settings(coarse_search_dims=2048)

    def test_singleton(self):
        a = get_settings()
        b = get_settings()
        assert a is b

    def test_reset(self):
        a = get_settings()
        reset_settings()
        b = get_settings()
        assert a is not b

    def test_override(self):
        s = get_settings(fine_search_top_k=10)
        assert s.fine_search_top_k == 10
