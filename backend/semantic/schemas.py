"""Typed containers for semantic reranking data flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MultiViewPrompts:
    """Stores the three prompt views for one POI.

    These correspond to the inference-time adaptation of POI-Enhancer-inspired
    views:
    - visit_pattern
    - location
    - category
    """

    visit_pattern: str
    location: str
    category: str

    def as_ordered_list(self) -> list[str]:
        return [self.visit_pattern, self.location, self.category]


@dataclass
class CandidatePOI:
    """Candidate packaged from SBR output plus metadata used for reranking."""

    rank: int
    item_id: int | None
    score: float
    raw_location_id: int
    poi_metadata: dict[str, Any]
    normalized_sbr_score: float = 0.0
    semantic_score: float = 0.0
    final_score: float = 0.0
    prompts: MultiViewPrompts | None = None
    descriptions: dict[str, Any] | None = None
    description_backend: str | None = None
    llm_rank: int | None = None
    llm_rank_score: float = 0.0
    rerank_source: str | None = None


@dataclass
class UserSemanticProfile:
    """Aggregated semantic representation derived from historical POIs."""

    user_id: int
    history_poi_ids: list[int] = field(default_factory=list)
    used_history_count: int = 0
    vector: Any = None


@dataclass
class RerankResult:
    """Top-level reranking result."""

    predictions: list[dict[str, Any]]
    used_semantic_reranker: bool
    debug: dict[str, Any] = field(default_factory=dict)
