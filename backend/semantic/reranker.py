"""Inference-time semantic reranker for top-k SBR candidates.

Pipeline summary:
1. Package SBR candidates with POI metadata.
2. Build three prompt views per POI.
3. Embed prompts through an abstract embedder.
4. Fuse view embeddings into one semantic POI representation.
5. Aggregate recent user history POIs into a user semantic vector.
6. Combine normalized SBR score and semantic similarity for final reranking.

What is intentionally not implemented from the full POI-Enhancer paper:
- Dual Feature Alignment
- Cross Attention Fusion
- Multi-View Contrastive Learning
- Any additional training-time optimization or frozen-LLM hidden-state pipeline
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from .config import SemanticRerankerConfig
from .embedder import build_embedder
from .fusion import WeightedSemanticFusion
from .prompt_builder import build_views
from .schemas import CandidatePOI, RerankResult, UserSemanticProfile
from .utils import average_vectors, cosine_similarity, min_max_normalize

if TYPE_CHECKING:
    from database import POI, UserHist


def package_candidates(predictions: list[dict[str, Any]], poi_by_id: dict[int, Any]) -> list[CandidatePOI]:
    """Stage A: package predictions with POI metadata for semantic reranking."""
    packaged: list[CandidatePOI] = []
    for index, pred in enumerate(predictions, start=1):
        raw_id = pred.get("raw_location_id")
        if raw_id is None:
            continue
        poi = poi_by_id.get(int(raw_id))
        poi_metadata = poi.to_dict() if poi else {
            "raw_poi_id": raw_id,
            "item_id": pred.get("item_id"),
            "category_name": None,
        }
        packaged.append(
            CandidatePOI(
                rank=int(pred.get("rank", index)),
                item_id=pred.get("item_id"),
                score=float(pred.get("score", 0.0)),
                raw_location_id=int(raw_id),
                poi_metadata=poi_metadata,
            )
        )
    return packaged


def _build_prompts_and_vectors_for_candidates(
    candidates: list[CandidatePOI],
    embedder,
    fusion: WeightedSemanticFusion,
) -> dict[int, np.ndarray]:
    """Batch-build prompts, batch-embed them, and fuse one semantic vector per candidate."""
    if not candidates:
        return {}

    all_texts: list[str] = []
    per_candidate_prompts = []

    for candidate in candidates:
        prompts = build_views(candidate.poi_metadata)
        candidate.prompts = prompts
        ordered = prompts.as_ordered_list()
        per_candidate_prompts.append((candidate, ordered))
        all_texts.extend(ordered)

    all_embeddings = embedder.embed_texts(all_texts)
    if len(all_embeddings) != len(all_texts):
        raise ValueError(
            f"Embedding count mismatch: got {len(all_embeddings)} embeddings for {len(all_texts)} prompts."
        )

    fused_vectors: dict[int, np.ndarray] = {}
    offset = 0
    for candidate, ordered in per_candidate_prompts:
        n = len(ordered)  # expected 3
        emb_slice = all_embeddings[offset: offset + n]
        offset += n

        if len(emb_slice) != 3:
            raise ValueError(
                f"Expected exactly 3 prompt embeddings per candidate, got {len(emb_slice)}."
            )

        fused_vectors[int(candidate.raw_location_id)] = fusion.fuse(
            emb_slice[0],
            emb_slice[1],
            emb_slice[2],
        )

    return fused_vectors


def _build_prompts_and_vectors_for_history(
    history_poi_metadata: list[dict[str, Any]],
    embedder,
    fusion: WeightedSemanticFusion,
) -> tuple[list[int], list[np.ndarray]]:
    """Batch-build and batch-embed history POI prompts."""
    if not history_poi_metadata:
        return [], []

    all_texts: list[str] = []
    history_ids: list[int] = []
    per_history_prompts: list[list[str]] = []

    for metadata in history_poi_metadata:
        raw_poi_id = metadata.get("raw_poi_id")
        if raw_poi_id is None:
            continue

        prompts = build_views(metadata)
        ordered = prompts.as_ordered_list()
        history_ids.append(int(raw_poi_id))
        per_history_prompts.append(ordered)
        all_texts.extend(ordered)

    if not all_texts:
        return history_ids, []

    all_embeddings = embedder.embed_texts(all_texts)
    if len(all_embeddings) != len(all_texts):
        raise ValueError(
            f"Embedding count mismatch: got {len(all_embeddings)} embeddings for {len(all_texts)} prompts."
        )

    vectors: list[np.ndarray] = []
    offset = 0
    for ordered in per_history_prompts:
        n = len(ordered)  # expected 3
        emb_slice = all_embeddings[offset: offset + n]
        offset += n

        if len(emb_slice) != 3:
            raise ValueError(
                f"Expected exactly 3 prompt embeddings per history POI, got {len(emb_slice)}."
            )

        vectors.append(
            fusion.fuse(
                emb_slice[0],
                emb_slice[1],
                emb_slice[2],
            )
        )

    return history_ids, vectors


def build_user_semantic_profile(
    user_id: int,
    history_poi_metadata: list[dict[str, Any]],
    embedder,
    fusion: WeightedSemanticFusion,
) -> UserSemanticProfile:
    """Stage E: aggregate historical POI semantics into a user semantic vector."""
    history_ids, history_vectors = _build_prompts_and_vectors_for_history(
        history_poi_metadata=history_poi_metadata,
        embedder=embedder,
        fusion=fusion,
    )

    return UserSemanticProfile(
        user_id=user_id,
        history_poi_ids=history_ids,
        used_history_count=len(history_ids),
        vector=average_vectors(history_vectors),
    )


def rerank_packaged_candidates(
    user_id: int,
    candidates: list[CandidatePOI],
    history_poi_metadata: list[dict[str, Any]],
    config: SemanticRerankerConfig | None = None,
) -> dict[str, Any]:
    """Rerank already-packaged candidates and return a serializable result."""
    config = config or SemanticRerankerConfig()

    embedder = build_embedder(
        config.SEMANTIC_EMBEDDING_BACKEND,
        embedding_dim=config.SEMANTIC_EMBEDDING_DIM,
    )
    fusion = WeightedSemanticFusion(config.SEMANTIC_VIEW_WEIGHTS)

    user_profile = build_user_semantic_profile(
        user_id=user_id,
        history_poi_metadata=history_poi_metadata,
        embedder=embedder,
        fusion=fusion,
    )

    sbr_scores = [candidate.score for candidate in candidates]
    normalized_scores = min_max_normalize(sbr_scores)

    candidate_vectors = _build_prompts_and_vectors_for_candidates(
        candidates=candidates,
        embedder=embedder,
        fusion=fusion,
    )

    for candidate, normalized_score in zip(candidates, normalized_scores):
        candidate.normalized_sbr_score = float(normalized_score)
        semantic_vector = candidate_vectors.get(int(candidate.raw_location_id))

        if semantic_vector is None or user_profile.vector is None:
            candidate.semantic_score = 0.0
        else:
            candidate.semantic_score = cosine_similarity(user_profile.vector, semantic_vector)

        candidate.final_score = (
            config.SEMANTIC_ALPHA * candidate.normalized_sbr_score
            + config.SEMANTIC_BETA * candidate.semantic_score
        )

    ranked_candidates = sorted(
        candidates,
        key=lambda candidate: (-candidate.final_score, -candidate.score, candidate.rank),
    )

    reranked_predictions = []
    for new_rank, candidate in enumerate(ranked_candidates, start=1):
        reranked_predictions.append(
            {
                "rank": new_rank,
                "item_id": candidate.item_id,
                "score": candidate.score,
                "raw_location_id": candidate.raw_location_id,
                "normalized_sbr_score": candidate.normalized_sbr_score,
                "semantic_score": candidate.semantic_score,
                "final_score": candidate.final_score,
            }
        )

    result = RerankResult(
        predictions=reranked_predictions,
        used_semantic_reranker=True,
        debug={
            "user_id": user_id,
            "used_history_count": user_profile.used_history_count,
            "semantic_backend": config.SEMANTIC_EMBEDDING_BACKEND,
            "view_weights": config.SEMANTIC_VIEW_WEIGHTS,
        },
    )
    return {
        "predictions": result.predictions,
        "used_semantic_reranker": result.used_semantic_reranker,
        "debug": result.debug,
    }


def rerank_predictions_for_user(
    user_id: int,
    predictions: list[dict[str, Any]],
    histories: list[UserHist] | None = None,
    config: SemanticRerankerConfig | None = None,
) -> list[dict[str, Any]]:
    """Stage F: end-to-end semantic reranking over top-k SBR predictions.

    This function is designed for direct integration in model_api.py after the
    prediction JSON has been loaded and before the final DB-backed response list
    is serialized for the frontend.
    """
    config = config or SemanticRerankerConfig()
    if not config.ENABLE_SEMANTIC_RERANKER:
        return predictions

    from database import POI, UserHist

    histories = histories or (
        UserHist.query.filter_by(user_id=user_id).order_by(UserHist.visit_time.desc()).all()
    )
    truncated_histories = histories[: config.SEMANTIC_MAX_HISTORY_ITEMS]

    raw_ids = [int(pred["raw_location_id"]) for pred in predictions if "raw_location_id" in pred]
    history_poi_ids = [int(hist.poi_id) for hist in truncated_histories if hist.poi_id is not None]
    all_needed_ids = sorted(set(raw_ids + history_poi_ids))
    if not all_needed_ids:
        return predictions

    pois = POI.query.filter(POI.id.in_(all_needed_ids)).all()
    poi_by_id = {int(poi.id): poi for poi in pois}

    candidates = package_candidates(predictions, poi_by_id)
    if not candidates:
        return predictions

    history_poi_metadata = [
        poi_by_id[poi_id].to_dict()
        for poi_id in history_poi_ids
        if poi_id in poi_by_id
    ]

    rerank_result = rerank_packaged_candidates(
        user_id=user_id,
        candidates=candidates,
        history_poi_metadata=history_poi_metadata,
        config=config,
    )
    return rerank_result["predictions"]