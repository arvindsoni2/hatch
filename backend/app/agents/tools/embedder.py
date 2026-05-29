"""Local sentence-transformer embedder for semantic job scoring.

Provides a singleton SentenceTransformer model with helpers for embedding
single texts, batches, and computing cosine similarity.

The model (all-MiniLM-L6-v2) produces 384-dimensional float vectors.
It is loaded lazily on first use and reused for the lifetime of the process.
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"

# Singleton model instance — None until first embed() call
_model = None  # type: ignore[assignment]

try:
    from sentence_transformers import SentenceTransformer
    _ST_AVAILABLE = True
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment,misc]
    _ST_AVAILABLE = False


def _get_model():  # type: ignore[return]
    """Lazy-load and return the singleton SentenceTransformer model.

    Returns:
        Loaded SentenceTransformer instance.

    Raises:
        RuntimeError: If sentence-transformers package is not installed.
    """
    global _model

    if not _ST_AVAILABLE:
        logger.warning(
            "sentence-transformers is not installed. "
            "Semantic scoring will not be available."
        )
        raise RuntimeError(
            "sentence-transformers is required for semantic scoring. "
            "Install with: pip install 'sentence-transformers>=3.0'"
        )

    if _model is None:
        logger.info("Loading sentence-transformer model: %s", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("Model loaded: %s", _MODEL_NAME)

    return _model


def embed(text: str) -> list[float]:
    """Embed a single text string into a float vector.

    Args:
        text: Input text to embed.

    Returns:
        384-dimensional float list.

    Raises:
        RuntimeError: If sentence-transformers is not installed.
    """
    model = _get_model()
    vector = model.encode(text, convert_to_numpy=True)
    return [float(x) for x in vector]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts.

    Args:
        texts: List of input strings.

    Returns:
        List of 384-dimensional float lists, one per input.

    Raises:
        RuntimeError: If sentence-transformers is not installed.
    """
    model = _get_model()
    vectors = model.encode(texts, convert_to_numpy=True)
    return [[float(x) for x in v] for v in vectors]


def cosine(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First float vector.
        b: Second float vector.

    Returns:
        Cosine similarity in [-1, 1].  Returns 0.0 for zero vectors.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector dimension mismatch: {len(a)} vs {len(b)}")

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)
