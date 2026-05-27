"""Text encoders for POI semantic prompt embeddings.

Stage 2 M2 only: encode prompt text into fixed vectors. Llama hidden-state
encoding is intentionally out of scope for this module version.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import numpy as np


DEFAULT_SENTENCE_TRANSFORMER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
PROMPT_PREFIX_NONE = "none"
PROMPT_PREFIX_E5 = "e5"
PROMPT_PREFIX_AUTO = "auto"


class BaseTextEncoder(ABC):
    """Common text embedding interface."""

    @property
    @abstractmethod
    def encoder_name(self) -> str:
        """Human-readable encoder backend name."""

    @property
    @abstractmethod
    def embedding_dim(self) -> int | None:
        """Embedding dimension when available."""

    @abstractmethod
    def encode_texts(self, texts: list[str], batch_size: int = 128) -> np.ndarray:
        """Encode text strings into a float32 matrix."""


class MockTextEncoder(BaseTextEncoder):
    """Deterministic hash-based encoder for smoke tests."""

    def __init__(self, embedding_dim: int = 128):
        if embedding_dim <= 0:
            raise ValueError("embedding_dim must be positive")
        self._embedding_dim = int(embedding_dim)

    @property
    def encoder_name(self) -> str:
        return "mock"

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    def encode_texts(self, texts: list[str], batch_size: int = 128) -> np.ndarray:
        if not texts:
            return np.empty((0, self.embedding_dim), dtype=np.float32)
        vectors = [self._encode_one(str(text)) for text in texts]
        return np.vstack(vectors).astype(np.float32, copy=False)

    def _encode_one(self, text: str) -> np.ndarray:
        values: list[int] = []
        counter = 0
        while len(values) < self.embedding_dim:
            payload = f"{text}\0{counter}".encode("utf-8")
            digest = hashlib.sha256(payload).digest()
            values.extend(np.frombuffer(digest, dtype=np.uint32).tolist())
            counter += 1

        arr = np.asarray(values[: self.embedding_dim], dtype=np.float32)
        arr = (arr / np.float32(np.iinfo(np.uint32).max)) * 2.0 - 1.0
        return _l2_normalize_matrix(arr.reshape(1, -1))[0]


class SentenceTransformerTextEncoder(BaseTextEncoder):
    """sentence-transformers encoder wrapper."""

    def __init__(
        self,
        model_name: str = DEFAULT_SENTENCE_TRANSFORMER_MODEL,
        device: str = "cuda",
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
        prompt_prefix_mode: str = PROMPT_PREFIX_AUTO,
        text_role: str = "passage",
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "Please install sentence-transformers before running semantic embedding precomputation."
            ) from exc

        self.model_name = model_name
        self.device = device
        self.normalize_embeddings = bool(normalize_embeddings)
        self.show_progress_bar = bool(show_progress_bar)
        self.prompt_prefix_mode = resolve_prompt_prefix_mode(prompt_prefix_mode, model_name)
        self.text_role = normalize_text_role(text_role)
        self.model = SentenceTransformer(model_name, device=device)
        dim = self.model.get_sentence_embedding_dimension()
        self._embedding_dim = int(dim) if dim is not None else None

    @property
    def encoder_name(self) -> str:
        return "sentence-transformer"

    @property
    def embedding_dim(self) -> int | None:
        return self._embedding_dim

    def encode_texts(self, texts: list[str], batch_size: int = 128) -> np.ndarray:
        if not texts:
            dim = self.embedding_dim or 0
            return np.empty((0, dim), dtype=np.float32)

        prepared_texts = apply_prompt_prefixes(
            list(texts),
            prompt_prefix_mode=self.prompt_prefix_mode,
            text_role=self.text_role,
        )
        embeddings = self.model.encode(
            prepared_texts,
            batch_size=int(batch_size),
            convert_to_numpy=True,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=self.show_progress_bar,
        )
        embeddings = np.asarray(embeddings, dtype=np.float32)
        if self.normalize_embeddings:
            embeddings = _l2_normalize_matrix(embeddings)
        return embeddings.astype(np.float32, copy=False)


def build_text_encoder(
    encoder_name: str,
    model_name: str | None,
    device: str,
    embedding_dim: int = 128,
    normalize_embeddings: bool = True,
    prompt_prefix_mode: str = PROMPT_PREFIX_AUTO,
    text_role: str = "passage",
) -> BaseTextEncoder:
    """Build a supported text encoder by backend name."""

    normalized_name = str(encoder_name).strip().lower().replace("_", "-")
    if normalized_name == "mock":
        return MockTextEncoder(embedding_dim=embedding_dim)
    if normalized_name in {"sentence-transformer", "hf", "huggingface"}:
        return SentenceTransformerTextEncoder(
            model_name=model_name or DEFAULT_SENTENCE_TRANSFORMER_MODEL,
            device=device,
            normalize_embeddings=normalize_embeddings,
            show_progress_bar=True,
            prompt_prefix_mode=prompt_prefix_mode,
            text_role=text_role,
        )
    raise ValueError(
        "Unsupported encoder_name. Expected one of: mock, sentence-transformer, "
        "sentence_transformer, hf, huggingface."
    )


def ensure_l2_normalized(embeddings: np.ndarray) -> np.ndarray:
    """Return a float32 L2-normalized copy of an embedding matrix."""

    return _l2_normalize_matrix(np.asarray(embeddings, dtype=np.float32))


def resolve_prompt_prefix_mode(prompt_prefix_mode: str, model_name: str | None = None) -> str:
    """Resolve auto prefix behavior for sentence-transformer encoders."""

    mode = str(prompt_prefix_mode or PROMPT_PREFIX_AUTO).strip().lower().replace("_", "-")
    if mode in {PROMPT_PREFIX_NONE, "off", "no-prefix"}:
        return PROMPT_PREFIX_NONE
    if mode in {PROMPT_PREFIX_E5, "e5-style"}:
        return PROMPT_PREFIX_E5
    if mode != PROMPT_PREFIX_AUTO:
        raise ValueError("prompt_prefix_mode must be one of: auto, none, e5")

    model = str(model_name or "").lower()
    if "e5" in model:
        return PROMPT_PREFIX_E5
    return PROMPT_PREFIX_NONE


def normalize_text_role(text_role: str) -> str:
    role = str(text_role or "passage").strip().lower()
    if role in {"candidate", "poi", "document", "doc"}:
        return "passage"
    if role in {"session", "query"}:
        return "query"
    if role not in {"passage", "query"}:
        raise ValueError("text_role must be one of: passage, query")
    return role


def apply_prompt_prefixes(
    texts: list[str],
    prompt_prefix_mode: str = PROMPT_PREFIX_NONE,
    text_role: str = "passage",
) -> list[str]:
    """Apply model-family prompt prefixes before embedding text."""

    mode = resolve_prompt_prefix_mode(prompt_prefix_mode)
    role = normalize_text_role(text_role)
    if mode == PROMPT_PREFIX_NONE:
        return [str(text) for text in texts]
    prefix = "query: " if role == "query" else "passage: "
    return [ensure_prefix(str(text), prefix) for text in texts]


def ensure_prefix(text: str, prefix: str) -> str:
    stripped = str(text).strip()
    if stripped.lower().startswith(prefix.lower()):
        return stripped
    return f"{prefix}{stripped}"


def _l2_normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.size == 0:
        return matrix.astype(np.float32, copy=False)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe_norms = np.where(norms > 0.0, norms, 1.0)
    normalized = matrix / safe_norms
    zero_rows = np.squeeze(norms, axis=1) == 0.0
    if np.any(zero_rows) and normalized.shape[1] > 0:
        normalized[zero_rows, 0] = 1.0
    return normalized.astype(np.float32, copy=False)
