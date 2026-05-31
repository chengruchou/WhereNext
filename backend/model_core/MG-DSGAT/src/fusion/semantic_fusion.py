"""Training-free semantic fusion reranking."""

from __future__ import annotations

from typing import Any

import numpy as np

from fusion.training_free import min_max_normalize


def ensure_base_fusion_score(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach base_fusion_score while preserving all existing candidate fields."""

    rows = [dict(candidate) for candidate in candidates]
    needs_normalized = any(row.get("normalized_sbr_score") is None for row in rows)
    if needs_normalized:
        _attach_normalized_sbr_scores(rows)

    for row in rows:
        if row.get("spatial_fusion_score") is not None:
            base_score = float(row["spatial_fusion_score"])
        elif row.get("normalized_sbr_score") is not None:
            base_score = float(row["normalized_sbr_score"])
        else:
            base_score = 0.0
        row["base_fusion_score"] = base_score
    return rows


def rank_by_semantic_fusion(
    candidates: list[dict[str, Any]],
    gamma_base: float = 0.95,
    semantic_weight: float | None = None,
    missing_semantic_policy: str = "base_only",
) -> list[dict[str, Any]]:
    """Rank candidates by conservative base-score plus semantic-score fusion."""

    if semantic_weight is None:
        semantic_weight = 1.0 - float(gamma_base)
    missing_semantic_policy = str(missing_semantic_policy)
    if missing_semantic_policy not in {"base_only", "zero", "mean"}:
        raise ValueError("missing_semantic_policy must be one of: base_only, zero, mean")

    rows = ensure_base_fusion_score(candidates)
    valid_semantic_scores = [
        float(row.get("semantic_score", 0.0))
        for row in rows
        if row.get("semantic_embedding_found") and row.get("semantic_score") is not None
    ]
    mean_semantic_score = float(np.mean(valid_semantic_scores)) if valid_semantic_scores else 0.0

    for input_order, row in enumerate(rows):
        row["_semantic_input_order"] = input_order
        base_score = float(row.get("base_fusion_score", 0.0))
        semantic_score = _semantic_score_for_row(
            row,
            base_score=base_score,
            mean_semantic_score=mean_semantic_score,
            missing_semantic_policy=missing_semantic_policy,
        )
        if row.get("_semantic_base_only"):
            fusion_score = base_score
        else:
            fusion_score = float(gamma_base) * base_score + float(semantic_weight) * semantic_score
        row["semantic_fusion_score"] = float(fusion_score)
        row["final_score"] = float(fusion_score)
        row["rerank_source"] = "semantic_fusion"

    rows.sort(key=_semantic_fusion_sort_key)
    for rank, row in enumerate(rows, start=1):
        row["semantic_final_rank"] = rank
        row["final_rank"] = rank
        row["rank"] = rank
        row.pop("_semantic_input_order", None)
        row.pop("_semantic_base_only", None)
    return rows


def rank_by_three_way_semantic_fusion(
    candidates: list[dict[str, Any]],
    alpha_sbr: float,
    beta_spatial: float,
    gamma_semantic: float,
) -> list[dict[str, Any]]:
    """Rank candidates by SBR, spatial, and semantic scores."""

    rows = [dict(candidate) for candidate in candidates]
    _attach_normalized_sbr_scores(rows)
    for input_order, row in enumerate(rows):
        normalized_sbr_score = float(row.get("normalized_sbr_score", 0.0) or 0.0)
        spatial_score = float(row.get("spatial_score", 0.0) or 0.0)
        semantic_score = (
            float(row.get("semantic_score", 0.0) or 0.0)
            if row.get("semantic_embedding_found")
            else 0.0
        )
        final_score = (
            float(alpha_sbr) * normalized_sbr_score
            + float(beta_spatial) * spatial_score
            + float(gamma_semantic) * semantic_score
        )
        row["_semantic_input_order"] = input_order
        row["base_fusion_score"] = normalized_sbr_score
        row["semantic_fusion_score"] = float(final_score)
        row["final_score"] = float(final_score)
        row["rerank_source"] = "semantic_three_way_fusion"

    rows.sort(key=_semantic_fusion_sort_key)
    for rank, row in enumerate(rows, start=1):
        row["semantic_final_rank"] = rank
        row["final_rank"] = rank
        row["rank"] = rank
        row.pop("_semantic_input_order", None)
    return rows


def semantic_score_diagnostics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize semantic score coverage and distribution for candidates."""

    found_rows = [
        row
        for row in candidates
        if row.get("semantic_embedding_found") and row.get("semantic_score") is not None
    ]
    scores = np.asarray([float(row["semantic_score"]) for row in found_rows], dtype=np.float32)
    if scores.size == 0:
        return {
            "candidate_count": len(candidates),
            "semantic_found_count": 0,
            "semantic_missing_count": len(candidates),
            "semantic_score_min": None,
            "semantic_score_mean": None,
            "semantic_score_max": None,
            "semantic_score_std": None,
            "semantic_score_range": None,
            "semantic_top1_item_id": None,
            "semantic_top1_score": None,
        }

    top_row = max(found_rows, key=lambda row: (float(row["semantic_score"]), -int(row.get("item_id", 10**12))))
    return {
        "candidate_count": len(candidates),
        "semantic_found_count": len(found_rows),
        "semantic_missing_count": len(candidates) - len(found_rows),
        "semantic_score_min": float(np.min(scores)),
        "semantic_score_mean": float(np.mean(scores)),
        "semantic_score_max": float(np.max(scores)),
        "semantic_score_std": float(np.std(scores)),
        "semantic_score_range": float(np.max(scores) - np.min(scores)),
        "semantic_top1_item_id": (
            int(top_row["item_id"]) if top_row.get("item_id") is not None else None
        ),
        "semantic_top1_score": float(top_row["semantic_score"]),
    }


def _attach_normalized_sbr_scores(rows: list[dict[str, Any]]) -> None:
    sbr_rows = []
    for row in rows:
        source = row.get("candidate_source")
        if row.get("sbr_score") is not None or source in {"sbr", "sbr+spatial"}:
            sbr_rows.append(row)
        elif row.get("score") is not None and source != "spatial":
            sbr_rows.append(row)
    scores = []
    keys = []
    for row in sbr_rows:
        score = row.get("sbr_score")
        if score is None:
            score = row.get("score")
        if score is None:
            continue
        scores.append(float(score))
        keys.append(_candidate_key(row))

    normalized_by_key: dict[tuple[str, int], float] = {}
    for key, normalized_score in zip(keys, min_max_normalize(scores)):
        if key is not None:
            normalized_by_key[key] = float(normalized_score)

    for row in rows:
        key = _candidate_key(row)
        row["normalized_sbr_score"] = (
            float(normalized_by_key.get(key, 0.0)) if key is not None else 0.0
        )


def _semantic_score_for_row(
    row: dict[str, Any],
    base_score: float,
    mean_semantic_score: float,
    missing_semantic_policy: str,
) -> float:
    if row.get("semantic_embedding_found") and row.get("semantic_score") is not None:
        row["_semantic_base_only"] = False
        return float(row["semantic_score"])
    if missing_semantic_policy == "base_only":
        row["_semantic_base_only"] = True
        return base_score
    row["_semantic_base_only"] = False
    if missing_semantic_policy == "mean":
        return mean_semantic_score
    return 0.0


def _semantic_fusion_sort_key(row: dict[str, Any]) -> tuple[float, float, int, int, int, int]:
    return (
        -float(row.get("semantic_fusion_score", 0.0)),
        -float(row.get("base_fusion_score", 0.0)),
        _rank_or_large(row.get("original_sbr_rank", row.get("sbr_rank"))),
        _rank_or_large(row.get("spatial_rank")),
        _rank_or_large(row.get("item_id")),
        int(row.get("_semantic_input_order", 10**9)),
    )


def _rank_or_large(value: Any) -> int:
    if value is None:
        return 10**9
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10**9


def _candidate_key(row: dict[str, Any]) -> tuple[str, int] | None:
    item_id = row.get("item_id")
    if item_id is not None:
        try:
            return ("item_id", int(item_id))
        except (TypeError, ValueError):
            pass
    raw_id = row.get("raw_location_id")
    if raw_id is not None:
        try:
            return ("raw_location_id", int(raw_id))
        except (TypeError, ValueError):
            pass
    return None
