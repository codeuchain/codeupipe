"""Embedding generation using Snowflake Arctic model.

Singleton embedder that loads the model once and reuses it.
Uses Matryoshka Representation Learning (MRL) which allows
comparing vectors at different dimensionalities for speed.

Install the discovery extras to use this module:
    pip install codeupipe[ai-discovery]
"""

from __future__ import annotations

import numpy as np

from codeupipe.ai.config import get_settings

# Lazy-loaded — set by _load_model() on first use.
# Declared at module level so tests can mock them.
AutoModel = None
AutoTokenizer = None


class SnowflakeArcticEmbedder:
    """Singleton embedder for Snowflake Arctic Embed L v2.0.

    Features:
        - 1024-dimensional output vectors
        - MRL support (truncate to 256 dims for fast coarse search)
        - CLS token extraction with L2 normalisation
        - Query prefix ("query: ") for asymmetric retrieval

    Usage:
        embedder = SnowflakeArcticEmbedder()
        q_vec = embedder.embed_query("calculate the sum")    # query → retrieval
        d_vec = embedder.embed_document("adds two numbers")  # document → indexing
    """

    _instance: SnowflakeArcticEmbedder | None = None
    _model = None
    _tokenizer = None

    QUERY_PREFIX = "query: "

    @property
    def model_name(self) -> str:
        """Model identifier from settings."""
        return get_settings().embedding_model

    def __new__(cls) -> SnowflakeArcticEmbedder:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._model is None:
            self._load_model()

    def _load_model(self) -> None:
        """Lazy-load the HuggingFace model and tokenizer."""
        global AutoModel, AutoTokenizer
        if AutoModel is None:
            try:
                from transformers import AutoModel as _AutoModel  # noqa: N814
                from transformers import AutoTokenizer as _AutoTokenizer  # noqa: N814
                AutoModel = _AutoModel
                AutoTokenizer = _AutoTokenizer
            except ImportError as exc:
                raise ImportError(
                    "Embedding requires torch and transformers. "
                    "Install with: pip install codeupipe[ai-discovery]"
                ) from exc

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModel.from_pretrained(self.model_name, add_pooling_layer=False)
        self._model.eval()

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a search query (with 'query: ' prefix for asymmetric retrieval).

        Args:
            query: Natural-language intent text.

        Returns:
            Normalised 1024-dim float32 numpy array.
        """
        return self._embed(f"{self.QUERY_PREFIX}{query}")

    def embed_document(self, text: str) -> np.ndarray:
        """Embed a document / capability description (no prefix).

        Args:
            text: Description text to index.

        Returns:
            Normalised 1024-dim float32 numpy array.
        """
        return self._embed(text)

    def _embed(self, text: str) -> np.ndarray:
        """Core embedding logic — tokenize → forward → CLS → normalise."""
        import torch

        tokens = self._tokenizer(
            [text],
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=8192,
        )

        with torch.no_grad():
            embedding = self._model(**tokens)[0][:, 0]  # CLS token
            embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)

        return embedding.numpy()[0]

    @classmethod
    def reset(cls) -> None:
        """Reset singleton — useful for testing."""
        cls._instance = None
        cls._model = None
        cls._tokenizer = None
