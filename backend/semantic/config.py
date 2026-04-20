"""Configuration for the inference-time semantic reranker.

The original POI-Enhancer work includes additional training-time modules such as
Dual Feature Alignment, Cross Attention Fusion, and contrastive learning. This
repository intentionally does not reproduce that full training stack. Instead,
the values below configure a lightweight inference-time adaptation that can be
upgraded later while preserving the same integration surface.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SemanticRerankerConfig:
    """Static configuration for semantic reranking."""

    ENABLE_SEMANTIC_RERANKER: bool = True
    SEMANTIC_ALPHA: float = 0.7 # weight for original SBR score vs. semantic similarity
    SEMANTIC_BETA: float = 0.3  # weight for visit pattern view vs. location and category views
    SEMANTIC_EMBEDDING_BACKEND: str = "hf"  # options: "mock", "hf", or a custom backend name
    SEMANTIC_MAX_HISTORY_ITEMS: int = 20
    SEMANTIC_EMBEDDING_DIM: int = 128
    SEMANTIC_VIEW_WEIGHTS: dict[str, float] = field(
        default_factory=lambda: {
            "visit_pattern": 0.45,
            "location": 0.25,
            "category": 0.30,
        }
    )

