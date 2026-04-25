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

from .cached_description_store import CachedDescriptionStore, build_description_cache_key
from .config import SemanticRerankerConfig
from .description_backend import build_description_generator
from .embedder import build_embedder
from .fusion import WeightedSemanticFusion
from .llm_reranker import LLMReranker
from .poi_description_generator import POIDescriptionGenerator
from .prompt_builder import build_views
from .score_fusion import fuse_scores, min_max_normalize as min_max_normalize_scores, rank_to_score
from .schemas import CandidatePOI, RerankResult, UserSemanticProfile
from .utils import average_vectors, cosine_similarity, min_max_normalize

if TYPE_CHECKING:
    from database import POI, UserHist


class _DictBackedPOI:
    """Small adapter so package_candidates can consume metadata dictionaries."""

    def __init__(self, metadata: dict[str, Any]):
        self.metadata = metadata

    def to_dict(self) -> dict[str, Any]:
        return self.metadata


def _format_visit_timestamp(value: Any) -> str | None:
    """Return a JSON-friendly timestamp string when one is available."""

    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


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


def prepare_poi_descriptions_for_candidates(
    candidates: list[CandidatePOI],
    cache_store,
    generator,
    dataset: str = "Gowalla",
    description_backend: str = "template",
    description_model_name: str | None = None,
    description_prompt_version: str = "v1",
) -> list[CandidatePOI]:
    """Attach cached or newly generated descriptions to candidates.

    This hook is optional and intentionally not called by the existing embedding
    reranker. If cache or generation fails, candidates are returned unchanged.
    """

    if not candidates:
        return candidates

    try:
        cache_store.load()
        model_name = (
            description_model_name
            if description_backend == "llama2"
            else "template"
        )
        key_by_raw_id = {}
        for candidate in candidates:
            metadata = dict(candidate.poi_metadata or {})
            metadata.setdefault("raw_poi_id", candidate.raw_location_id)
            metadata.setdefault("item_id", candidate.item_id)
            key_by_raw_id[int(candidate.raw_location_id)] = build_description_cache_key(
                poi_metadata=metadata,
                dataset=dataset,
                backend=description_backend,
                model_name=model_name,
                prompt_version=description_prompt_version,
            )
        cached_entries = cache_store.get_many(list(key_by_raw_id.values()))
        did_generate = False

        for candidate in candidates:
            key = key_by_raw_id[int(candidate.raw_location_id)]
            cached_entry = cached_entries.get(key)
            if cached_entry is not None:
                candidate.descriptions = cached_entry.get("descriptions")
                candidate.description_backend = cached_entry.get(
                    "description_backend",
                    description_backend,
                )
                continue

            try:
                descriptions = generator.generate_descriptions(candidate.poi_metadata)
            except Exception as exc:
                print(
                    "[Semantic] Description generation failed for "
                    f"raw_poi_id={candidate.raw_location_id}; using template fallback: {exc}"
                )
                descriptions = POIDescriptionGenerator().generate_descriptions(candidate.poi_metadata)
            candidate.descriptions = descriptions
            candidate.description_backend = description_backend
            cache_store.set(
                key,
                {
                    "raw_poi_id": candidate.raw_location_id,
                    "item_id": candidate.item_id,
                    "description_backend": description_backend,
                    "description_model_name": model_name,
                    "description_prompt_version": description_prompt_version,
                    "descriptions": descriptions,
                },
            )
            did_generate = True

        if did_generate:
            cache_store.save()
    except Exception as exc:
        print(f"[Semantic] Description preparation skipped: {exc}")

    return candidates


def _build_history_description_rows(
    history_pois: list[dict],
    cache_store: CachedDescriptionStore,
    generator,
    dataset: str = "Gowalla",
    description_backend: str = "template",
    description_model_name: str | None = None,
    description_prompt_version: str = "v1",
) -> list[dict[str, Any]]:
    """Generate cached description rows for ordered history POIs."""

    history_candidates: list[CandidatePOI] = []
    for index, metadata in enumerate(history_pois, start=1):
        raw_id = metadata.get("raw_poi_id") or metadata.get("id") or metadata.get("raw_location_id")
        if raw_id is None:
            continue
        history_candidates.append(
            CandidatePOI(
                rank=index,
                item_id=metadata.get("item_id"),
                score=0.0,
                raw_location_id=int(raw_id),
                poi_metadata=metadata,
            )
        )

    prepare_poi_descriptions_for_candidates(
        candidates=history_candidates,
        cache_store=cache_store,
        generator=generator,
        dataset=dataset,
        description_backend=description_backend,
        description_model_name=description_model_name,
        description_prompt_version=description_prompt_version,
    )

    return [
        {
            "raw_location_id": candidate.raw_location_id,
            "item_id": candidate.item_id,
            "timestamp": candidate.poi_metadata.get("timestamp"),
            "description_backend": candidate.description_backend,
            "descriptions": candidate.descriptions,
        }
        for candidate in history_candidates
        if candidate.descriptions is not None
    ]


def _candidate_to_prediction_dict(candidate: CandidatePOI) -> dict[str, Any]:
    """Serialize one LLM-reranked candidate."""

    return {
        "rank": candidate.rank,
        "item_id": candidate.item_id,
        "raw_location_id": candidate.raw_location_id,
        "score": candidate.score,
        "normalized_sbr_score": candidate.normalized_sbr_score,
        "llm_rank": candidate.llm_rank,
        "llm_rank_score": candidate.llm_rank_score,
        "final_score": candidate.final_score,
        "descriptions": candidate.descriptions,
        "description_backend": candidate.description_backend,
        "rerank_source": candidate.rerank_source,
    }


def _fallback_llm_predictions(candidates: list[CandidatePOI]) -> list[dict[str, Any]]:
    """Return original SBR order with normalized SBR scores and fallback source."""

    normalized_scores = min_max_normalize_scores([candidate.score for candidate in candidates])
    for candidate, normalized_score in zip(candidates, normalized_scores):
        candidate.normalized_sbr_score = float(normalized_score)
        candidate.llm_rank = None
        candidate.llm_rank_score = 0.0
        candidate.final_score = candidate.normalized_sbr_score
        candidate.rerank_source = "llm_fallback_sbr"

    return [
        _candidate_to_prediction_dict(candidate)
        for candidate in sorted(candidates, key=lambda item: item.rank)
    ]


def rerank_predictions_with_llm_for_user(
    predictions: list[dict],
    history_pois: list[dict],
    poi_metadata_by_raw_id: dict[int, dict],
    description_cache_path: str,
    llm_model_name: str = "gpt-4.1-mini",
    fusion_alpha: float = 0.7,
    max_candidates_for_llm: int = 10,
    description_backend: str = "template",
    description_model_name: str | None = None,
    description_prompt_version: str = "v1",
    description_use_4bit: bool = False,
    description_max_new_tokens: int = 220,
    description_temperature: float = 0.2,
    description_generator=None,
) -> list[dict]:
    """Optional listwise LLM reranking over SBR top-k predictions.

    This is intentionally separate from the existing embedding reranker. If
    anything fails, the function returns the original SBR order with diagnostic
    fallback fields instead of raising.
    """

    poi_by_id = {
        int(raw_id): _DictBackedPOI(metadata)
        for raw_id, metadata in poi_metadata_by_raw_id.items()
    }
    candidates = package_candidates(predictions, poi_by_id)
    if not candidates:
        return predictions
    for candidate in candidates:
        candidate.description_backend = description_backend

    try:
        cache_store = CachedDescriptionStore(description_cache_path)
        generator = description_generator or build_description_generator(
            backend=description_backend,
            model_name=description_model_name,
            prompt_version=description_prompt_version,
            use_4bit=description_use_4bit,
            max_new_tokens=description_max_new_tokens,
            temperature=description_temperature,
        )
        resolved_description_model_name = (
            description_model_name
            if description_backend == "llama2"
            else "template"
        )

        prepare_poi_descriptions_for_candidates(
            candidates=candidates,
            cache_store=cache_store,
            generator=generator,
            description_backend=description_backend,
            description_model_name=resolved_description_model_name,
            description_prompt_version=description_prompt_version,
        )
        history_descriptions = _build_history_description_rows(
            history_pois=history_pois,
            cache_store=cache_store,
            generator=generator,
            description_backend=description_backend,
            description_model_name=resolved_description_model_name,
            description_prompt_version=description_prompt_version,
        )

        candidate_prediction_rows = [
            {
                "rank": candidate.rank,
                "item_id": candidate.item_id,
                "score": candidate.score,
                "raw_location_id": candidate.raw_location_id,
                "description_backend": candidate.description_backend,
                "descriptions": candidate.descriptions,
            }
            for candidate in sorted(candidates, key=lambda item: item.rank)
        ]

        llm_reranker = LLMReranker(
            model_name=llm_model_name,
            max_candidates=max_candidates_for_llm,
        )
        llm_ranked_ids = llm_reranker.rerank(
            history_descriptions=history_descriptions,
            candidate_predictions=candidate_prediction_rows,
        )
        if llm_reranker.last_parse_failed:
            raise ValueError("LLM ranking response could not be parsed.")

        original_ids = [
            int(candidate.raw_location_id)
            for candidate in sorted(candidates, key=lambda item: item.rank)
        ]
        seen_ids = set(llm_ranked_ids)
        full_ranked_ids = llm_ranked_ids + [
            raw_id for raw_id in original_ids if raw_id not in seen_ids
        ]
        llm_rank_by_raw_id = {
            raw_id: index
            for index, raw_id in enumerate(full_ranked_ids, start=1)
        }

        n_candidates = len(candidates)
        normalized_scores = min_max_normalize_scores([candidate.score for candidate in candidates])
        for candidate, normalized_score in zip(candidates, normalized_scores):
            candidate.normalized_sbr_score = float(normalized_score)
            candidate.llm_rank = llm_rank_by_raw_id.get(
                int(candidate.raw_location_id),
                n_candidates,
            )
            candidate.llm_rank_score = rank_to_score(candidate.llm_rank, n_candidates)
            candidate.final_score = fuse_scores(
                normalized_sbr=candidate.normalized_sbr_score,
                llm_rank_score=candidate.llm_rank_score,
                alpha=fusion_alpha,
            )
            candidate.rerank_source = "llm_listwise"

        ranked_candidates = sorted(
            candidates,
            key=lambda candidate: (-candidate.final_score, -candidate.score, candidate.rank),
        )
        for new_rank, candidate in enumerate(ranked_candidates, start=1):
            candidate.rank = new_rank
        return [_candidate_to_prediction_dict(candidate) for candidate in ranked_candidates]

    except Exception as exc:
        print(f"[Semantic] LLM reranker fallback to original SBR order: {exc}")
        return _fallback_llm_predictions(candidates)


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
        prediction = {
            "rank": new_rank,
            "item_id": candidate.item_id,
            "score": candidate.score,
            "raw_location_id": candidate.raw_location_id,
            "normalized_sbr_score": candidate.normalized_sbr_score,
            "semantic_score": candidate.semantic_score,
            "final_score": candidate.final_score,
        }
        if candidate.descriptions is not None:
            prediction["descriptions"] = candidate.descriptions
        reranked_predictions.append(prediction)

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

    history_poi_metadata = []
    for hist in truncated_histories:
        if hist.poi_id is None:
            continue
        poi_id = int(hist.poi_id)
        if poi_id not in poi_by_id:
            continue
        metadata = dict(poi_by_id[poi_id].to_dict())
        timestamp = _format_visit_timestamp(getattr(hist, "visit_time", None))
        if timestamp is not None:
            metadata["timestamp"] = timestamp
        history_poi_metadata.append(metadata)

    rerank_result = rerank_packaged_candidates(
        user_id=user_id,
        candidates=candidates,
        history_poi_metadata=history_poi_metadata,
        config=config,
    )
    return rerank_result["predictions"]
