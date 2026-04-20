"""Semantic embedding backends for inference-time reranking.

This repository does not ship with a frozen LLM checkpoint or the original
POI-Enhancer implementation. To keep semantic reranking deployable in this
existing full-stack system, the default backend is a deterministic CPU-only mock
embedder based on hashed token features.

Where a real backend can be attached later:
- Create a concrete subclass of BaseSemanticEmbedder
- Load a sentence-transformer, Hugging Face encoder, or Llama-style embedding
  model in that subclass
- Return a NumPy array of shape (n_texts, embedding_dim) from embed_texts()

Important:
- HF/SentenceTransformer backends are cached at process level.
- That means the model is loaded only once per Python process.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from functools import lru_cache

import numpy as np


class BaseSemanticEmbedder(ABC):
    """Base embedder interface used by the reranker."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Convert input texts into an array of semantic embeddings."""
        raise NotImplementedError


class MockSemanticEmbedder(BaseSemanticEmbedder):
    """Deterministic CPU-only fallback embedder.

    This backend intentionally trades expressive model quality for portability and
    reproducibility. It converts tokens into a hashed bag-of-features vector and
    L2-normalizes the result so the reranker can use cosine similarity.
    """

    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        rows = [self._embed_single(text or "") for text in texts]
        if not rows:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        return np.vstack(rows).astype(np.float32)

    def _embed_single(self, text: str) -> np.ndarray:
        vector = np.zeros(self.embedding_dim, dtype=np.float32)
        tokens = self._tokenize(text)
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], byteorder="big") % self.embedding_dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + (digest[5] / 255.0)
            vector[bucket] += sign * weight

        norm = np.linalg.norm(vector)
        return vector if norm == 0 else vector / norm

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-z0-9_.-]+", text.lower())


class HuggingFaceSemanticEmbedder(BaseSemanticEmbedder):
    """SentenceTransformer-backed semantic embedder.

    This backend is cached via build_embedder(), so the model should only load
    once per Python process.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_embedding_dimension()

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.astype(np.float32)


@lru_cache(maxsize=8)
def _cached_embedder(backend_key: str, embedding_dim: int) -> BaseSemanticEmbedder:
    """Process-level embedder cache.

    For HF backends this ensures the model is loaded only once per process.
    """
    if backend_key == "mock":
        print("[Semantic] Initializing MockSemanticEmbedder once per process.")
        return MockSemanticEmbedder(embedding_dim=embedding_dim)

    if backend_key in {"hf", "huggingface", "transformers"}:
        print("[Semantic] Initializing HuggingFaceSemanticEmbedder once per process.")
        return HuggingFaceSemanticEmbedder()
    

    raise ValueError(f"Unsupported semantic embedding backend: {backend_key}")


def build_embedder(backend_name: str, embedding_dim: int = 128) -> BaseSemanticEmbedder:
    """Factory for semantic embedding backends.

    Returns a cached embedder instance per Python process.
    """
    backend_key = (backend_name or "mock").strip().lower()
    return _cached_embedder(backend_key, embedding_dim)