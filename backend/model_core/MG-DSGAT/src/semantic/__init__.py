"""Semantic prompt and embedding utilities for model-side reranking."""

from .prompt_builder import (
    PROMPT_VERSION,
    build_multi_view_prompts,
    build_poi_prompt,
    build_prompt_cache,
    metadata_hash,
    normalize_metadata_row,
    prompt_hash,
)
from .text_encoder import (
    BaseTextEncoder,
    MockTextEncoder,
    SentenceTransformerTextEncoder,
    build_text_encoder,
)
from .session_encoder import (
    build_multi_view_session_embeddings,
    build_session_embedding,
    last_n_history_item_ids,
    mean_pool_history_embeddings,
    recency_weighted_pool_history_embeddings,
)
from .similarity import (
    cosine_similarity_matrix,
    cosine_to_01,
    score_candidates_by_multiview_semantic_similarity,
    score_candidates_by_semantic_similarity,
)

__all__ = [
    "BaseTextEncoder",
    "MockTextEncoder",
    "PROMPT_VERSION",
    "SentenceTransformerTextEncoder",
    "build_multi_view_prompts",
    "build_multi_view_session_embeddings",
    "build_poi_prompt",
    "build_prompt_cache",
    "build_session_embedding",
    "build_text_encoder",
    "cosine_similarity_matrix",
    "cosine_to_01",
    "last_n_history_item_ids",
    "metadata_hash",
    "mean_pool_history_embeddings",
    "normalize_metadata_row",
    "prompt_hash",
    "recency_weighted_pool_history_embeddings",
    "score_candidates_by_semantic_similarity",
    "score_candidates_by_multiview_semantic_similarity",
]
