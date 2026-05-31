"""Training-free spatial fusion reranker."""

from __future__ import annotations

from typing import Any


def min_max_normalize(scores: list[float]) -> list[float]:
    """Normalize scores into [0, 1] with a stable equal-values fallback."""

    if not scores:
        return []
    values = [float(score) for score in scores]
    min_score = min(values)
    max_score = max(values)
    if max_score - min_score < 1e-12:
        return [1.0 for _ in values]
    return [(score - min_score) / (max_score - min_score) for score in values]


def rank_by_spatial_fusion(
    candidates: list[dict[str, Any]],
    alpha_sbr: float = 0.7,
    alpha_spatial: float = 0.3,
) -> list[dict[str, Any]]:
    """Rank candidates by normalized SBR score plus spatial score."""

    sbr_rows = [
        row
        for row in candidates
        if row.get("sbr_score") is not None
        or row.get("candidate_source") in {"sbr", "sbr+spatial"}
    ]
    normalized_sbr_by_key: dict[tuple[str, int], float] = {}
    normalized_scores = min_max_normalize(
        [float(row.get("sbr_score", row.get("score", 0.0))) for row in sbr_rows]
    )
    for row, normalized_score in zip(sbr_rows, normalized_scores):
        key = _candidate_key(row)
        if key is not None:
            normalized_sbr_by_key[key] = float(normalized_score)

    ranked_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        row = dict(candidate)
        key = _candidate_key(row)
        normalized_sbr_score = (
            normalized_sbr_by_key.get(key, 0.0) if key is not None else 0.0
        )
        spatial_score = float(row.get("spatial_score") or 0.0)
        fusion_score = float(alpha_sbr) * normalized_sbr_score + float(alpha_spatial) * spatial_score
        row["normalized_sbr_score"] = normalized_sbr_score
        row["spatial_fusion_score"] = fusion_score
        ranked_rows.append(row)

    ranked_rows.sort(
        key=lambda row: (
            -float(row.get("spatial_fusion_score", 0.0)),
            -float(row.get("sbr_score") if row.get("sbr_score") is not None else row.get("score", 0.0)),
            int(row.get("rank", 10**9)),
        )
    )
    for rank, row in enumerate(ranked_rows, start=1):
        row["final_rank"] = rank
        row["rank"] = rank
    return ranked_rows


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

