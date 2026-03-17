"""Unit tests for the SnowflakeArcticEmbedder.

These tests mock the heavy torch/transformers dependencies so the
test suite can run without downloading models.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from codeupipe.ai.config import reset_settings


@pytest.fixture(autouse=True)
def _clean_singleton():
    """Reset embedder and settings singletons between tests."""
    # Import here to avoid import errors when torch isn't installed
    from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder
    SnowflakeArcticEmbedder.reset()
    reset_settings()
    yield
    SnowflakeArcticEmbedder.reset()
    reset_settings()


def _mock_model_output(dim: int = 1024):
    """Create a mock model that returns a fake embedding tensor."""
    import torch

    fake_embedding = torch.randn(1, dim)
    fake_output = MagicMock()
    fake_output.__getitem__ = lambda self, idx: torch.randn(1, 10, dim) if idx == 0 else None

    # model(**tokens)[0][:, 0] should return shape (1, dim)
    class FakeModelOutput:
        def __getitem__(self, idx):
            if idx == 0:
                # Simulate (batch, seq_len, dim) → [:, 0] gives (batch, dim)
                return torch.stack([fake_embedding])
            raise IndexError

    model = MagicMock()
    model.return_value = FakeModelOutput()
    model.eval = MagicMock()
    return model


@patch("codeupipe.ai.discovery.embedder.AutoModel")
@patch("codeupipe.ai.discovery.embedder.AutoTokenizer")
def test_singleton_pattern(mock_tokenizer_cls, mock_model_cls):
    """Only one instance should be created."""
    mock_model_cls.from_pretrained.return_value = _mock_model_output()
    mock_tokenizer_cls.from_pretrained.return_value = MagicMock()

    from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder

    a = SnowflakeArcticEmbedder()
    b = SnowflakeArcticEmbedder()
    assert a is b


@patch("codeupipe.ai.discovery.embedder.AutoModel")
@patch("codeupipe.ai.discovery.embedder.AutoTokenizer")
def test_embed_query_returns_numpy(mock_tokenizer_cls, mock_model_cls):
    """embed_query should return a numpy array."""
    import torch

    mock_model = MagicMock()
    cls_output = torch.randn(1, 1024)
    seq_output = cls_output.unsqueeze(1)  # (1, 1, 1024)

    class FakeOutput:
        def __getitem__(self, idx):
            return seq_output

    mock_model.return_value = FakeOutput()
    mock_model.eval = MagicMock()
    mock_model_cls.from_pretrained.return_value = mock_model

    tokenizer = MagicMock()
    tokenizer.return_value = {"input_ids": torch.zeros(1, 5, dtype=torch.long)}
    mock_tokenizer_cls.from_pretrained.return_value = tokenizer

    from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder

    embedder = SnowflakeArcticEmbedder()
    result = embedder.embed_query("test query")

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32


@patch("codeupipe.ai.discovery.embedder.AutoModel")
@patch("codeupipe.ai.discovery.embedder.AutoTokenizer")
def test_embed_query_is_normalised(mock_tokenizer_cls, mock_model_cls):
    """Output vector should have unit norm (L2 normalised)."""
    import torch

    cls_output = torch.randn(1, 1024)
    seq_output = cls_output.unsqueeze(1)

    class FakeOutput:
        def __getitem__(self, idx):
            return seq_output

    mock_model = MagicMock()
    mock_model.return_value = FakeOutput()
    mock_model.eval = MagicMock()
    mock_model_cls.from_pretrained.return_value = mock_model

    tokenizer = MagicMock()
    tokenizer.return_value = {"input_ids": torch.zeros(1, 5, dtype=torch.long)}
    mock_tokenizer_cls.from_pretrained.return_value = tokenizer

    from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder

    embedder = SnowflakeArcticEmbedder()
    result = embedder.embed_query("test")
    norm = np.linalg.norm(result)
    assert abs(norm - 1.0) < 1e-5


@patch("codeupipe.ai.discovery.embedder.AutoModel")
@patch("codeupipe.ai.discovery.embedder.AutoTokenizer")
def test_embed_query_has_prefix(mock_tokenizer_cls, mock_model_cls):
    """Query embedding should prepend 'query: ' to the input text."""
    import torch

    cls_output = torch.randn(1, 1024)
    seq_output = cls_output.unsqueeze(1)

    class FakeOutput:
        def __getitem__(self, idx):
            return seq_output

    mock_model = MagicMock()
    mock_model.return_value = FakeOutput()
    mock_model.eval = MagicMock()
    mock_model_cls.from_pretrained.return_value = mock_model

    tokenizer = MagicMock()
    tokenizer.return_value = {"input_ids": torch.zeros(1, 5, dtype=torch.long)}
    mock_tokenizer_cls.from_pretrained.return_value = tokenizer

    from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder

    embedder = SnowflakeArcticEmbedder()
    embedder.embed_query("calculate sum")

    # Verify the tokenizer was called with 'query: ' prefix
    call_args = tokenizer.call_args
    assert call_args[0][0] == ["query: calculate sum"]


@patch("codeupipe.ai.discovery.embedder.AutoModel")
@patch("codeupipe.ai.discovery.embedder.AutoTokenizer")
def test_embed_document_no_prefix(mock_tokenizer_cls, mock_model_cls):
    """Document embedding should NOT have 'query: ' prefix."""
    import torch

    cls_output = torch.randn(1, 1024)
    seq_output = cls_output.unsqueeze(1)

    class FakeOutput:
        def __getitem__(self, idx):
            return seq_output

    mock_model = MagicMock()
    mock_model.return_value = FakeOutput()
    mock_model.eval = MagicMock()
    mock_model_cls.from_pretrained.return_value = mock_model

    tokenizer = MagicMock()
    tokenizer.return_value = {"input_ids": torch.zeros(1, 5, dtype=torch.long)}
    mock_tokenizer_cls.from_pretrained.return_value = tokenizer

    from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder

    embedder = SnowflakeArcticEmbedder()
    embedder.embed_document("adds two numbers")

    call_args = tokenizer.call_args
    assert call_args[0][0] == ["adds two numbers"]


@patch("codeupipe.ai.discovery.embedder.AutoModel")
@patch("codeupipe.ai.discovery.embedder.AutoTokenizer")
def test_model_name_from_settings(mock_tokenizer_cls, mock_model_cls):
    """Embedder should read model name from settings."""
    mock_model = MagicMock()
    mock_model.eval = MagicMock()
    mock_model_cls.from_pretrained.return_value = mock_model
    mock_tokenizer_cls.from_pretrained.return_value = MagicMock()

    from codeupipe.ai.discovery.embedder import SnowflakeArcticEmbedder

    embedder = SnowflakeArcticEmbedder()
    assert "snowflake" in embedder.model_name.lower()
