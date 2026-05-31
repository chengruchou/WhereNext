"""Semantic similarity scoring for candidate POIs."""

from __future__ import annotations

from typing import Any

import numpy as np


def cosine_similarity_matrix(query_embedding, candidate_embeddings) -> np.ndarray:
    """Compute cosine similarity between one query vector and candidate vectors."""

    query = np.asarray(query_embedding, dtype=np.float32)
    candidates = np.asarray(candidate_embeddings, dtype=np.float32)
    if query.ndim == 2:
        if query.shape[0] != 1:
            raise ValueError(f"query_embedding must have shape (d,) or (1, d), got {query.shape}")
        query = query[0]
    if query.ndim != 1:
        raise ValueError(f"query_embedding must have shape (d,) or (1, d), got {query.shape}")
    if candidates.ndim != 2:
        raise ValueError(f"candidate_embeddings must have shape (n, d), got {candidates.shape}")
    if candidates.shape[1] != query.shape[0]:
        raise ValueError(
            f"Embedding dimension mismatch: query dim {query.shape[0]}, "
            f"candidate dim {candidates.shape[1]}"
        )
    if candidates.shape[0] == 0:
        return np.asarray([], dtype=np.float32)

    query_norm = float(np.linalg.norm(query))
    candidate_norms = np.linalg.norm(candidates, axis=1)
    denominator = candidate_norms * query_norm
    scores = np.zeros(candidates.shape[0], dtype=np.float32)
    valid = denominator > 0.0
    if np.any(valid):
        scores[valid] = np.dot(candidates[valid], query) / denominator[valid]
    return np.clip(scores, -1.0, 1.0).astype(np.float32)


def cosine_to_01(scores: np.ndarray) -> np.ndarray:
    """Convert cosine similarity scores from [-1, 1] to [0, 1]."""

    scores = np.asarray(scores, dtype=np.float32)
    return np.clip((scores + 1.0) / 2.0, 0.0, 1.0).astype(np.float32)


def score_candidates_by_semantic_similarity(
    session_embedding,
    candidate_rows,
    embedding_store,
    view: str | None = None,
    score_field: str = "semantic_score",
    raw_score_field: str = "semantic_score_raw",
    found_field: str = "semantic_embedding_found",
    rank_field: str = "semantic_rank",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach semantic similarity scores to candidate rows without reordering them."""

    scored_rows = [dict(row) for row in candidate_rows]
    score_field = str(score_field)
    raw_score_field = str(raw_score_field)
    found_field = str(found_field)
    rank_field = str(rank_field)
    diagnostics: dict[str, Any] = {
        "candidate_count": len(scored_rows),
        "candidate_embedding_found_count": 0,
        "candidate_embedding_missing_count": 0,
        "missing_candidate_item_ids": [],
        "semantic_score_min": None,
        "semantic_score_mean": None,
        "semantic_score_max": None,
        "semantic_score_std": None,
        "status": "ok",
        "view": view,
    }

    for row in scored_rows:
        row[raw_score_field] = None
        row[score_field] = 0.0
        row[found_field] = False
        row[rank_field] = None

    valid_positions = []
    valid_embeddings = []
    missing_item_ids = []
    for index, row in enumerate(scored_rows):
        item_id = row.get("item_id")
        if item_id is None:
            missing_item_ids.append(None)
            continue
        item_id = int(item_id)
        if embedding_store.has_item_id(item_id, view=view):
            valid_positions.append(index)
            valid_embeddings.append(
                np.asarray(embedding_store.get_by_item_id(item_id, view=view), dtype=np.float32)
            )
            scored_rows[index][found_field] = True
        else:
            missing_item_ids.append(item_id)

    diagnostics["candidate_embedding_found_count"] = len(valid_positions)
    diagnostics["candidate_embedding_missing_count"] = len(scored_rows) - len(valid_positions)
    diagnostics["missing_candidate_item_ids"] = missing_item_ids[:50]

    if session_embedding is None:
        diagnostics["status"] = "no_session_embedding"
        _assign_semantic_ranks(scored_rows, score_field=score_field, found_field=found_field, rank_field=rank_field)
        return scored_rows, diagnostics

    if valid_embeddings:
        candidate_matrix = np.vstack(valid_embeddings).astype(np.float32)
        raw_scores = cosine_similarity_matrix(session_embedding, candidate_matrix)
        semantic_scores = cosine_to_01(raw_scores)
        for position, raw_score, semantic_score in zip(valid_positions, raw_scores, semantic_scores):
            scored_rows[position][raw_score_field] = float(raw_score)
            scored_rows[position][score_field] = float(semantic_score)
            scored_rows[position][found_field] = True

        diagnostics["semantic_score_min"] = float(np.min(semantic_scores))
        diagnostics["semantic_score_mean"] = float(np.mean(semantic_scores))
        diagnostics["semantic_score_max"] = float(np.max(semantic_scores))
        diagnostics["semantic_score_std"] = float(np.std(semantic_scores))

    _assign_semantic_ranks(scored_rows, score_field=score_field, found_field=found_field, rank_field=rank_field)
    return scored_rows, diagnostics


def score_candidates_by_multiview_semantic_similarity(
    session_embeddings_by_view: dict[str, np.ndarray | None],
    candidate_rows,
    embedding_store,
    view_weights: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach per-view scores and a weighted semantic_score to candidate rows."""

    scored_rows = [dict(row) for row in candidate_rows]
    diagnostics: dict[str, Any] = {
        "candidate_count": len(scored_rows),
        "view_weights": {str(view): float(weight) for view, weight in view_weights.items()},
        "views": {},
        "candidate_embedding_found_count": 0,
        "candidate_embedding_missing_count": 0,
        "missing_candidate_item_ids": [],
        "semantic_score_min": None,
        "semantic_score_mean": None,
        "semantic_score_max": None,
        "semantic_score_std": None,
        "status": "ok",
    }

    active_views = [
        str(view)
        for view, weight in view_weights.items()
        if str(view) in session_embeddings_by_view
    ]
    weight_sum = float(sum(max(0.0, float(view_weights[view])) for view in active_views))
    if weight_sum <= 0.0:
        diagnostics["status"] = "no_positive_view_weights"
        for row in scored_rows:
            row["semantic_score"] = 0.0
            row["semantic_score_raw"] = None
            row["semantic_embedding_found"] = False
            row["semantic_rank"] = None
        _assign_semantic_ranks(scored_rows)
        return scored_rows, diagnostics

    for row in scored_rows:
        row["semantic_score"] = 0.0
        row["semantic_score_raw"] = None
        row["semantic_embedding_found"] = False
        row["semantic_rank"] = None

    per_view_found_sets: list[set[int]] = []
    missing_by_view: dict[str, list[int | None]] = {}
    for view in active_views:
        suffix = _view_suffix(view)
        scored_rows, view_diag = score_candidates_by_semantic_similarity(
            session_embeddings_by_view.get(view),
            scored_rows,
            embedding_store,
            view=view,
            score_field=f"semantic_score_{suffix}",
            raw_score_field=f"semantic_score_raw_{suffix}",
            found_field=f"semantic_embedding_found_{suffix}",
            rank_field=f"semantic_rank_{suffix}",
        )
        diagnostics["views"][view] = view_diag
        missing_by_view[view] = list(view_diag.get("missing_candidate_item_ids", []))
        per_view_found_sets.append(
            {
                index
                for index, row in enumerate(scored_rows)
                if row.get(f"semantic_embedding_found_{suffix}")
            }
        )

    positive_weights = {
        view: max(0.0, float(view_weights[view])) / weight_sum for view in active_views
    }
    combined_scores = []
    found_any_count = 0
    for row in scored_rows:
        weighted_score = 0.0
        found_any = False
        raw_components = []
        for view in active_views:
            suffix = _view_suffix(view)
            if row.get(f"semantic_embedding_found_{suffix}"):
                score = float(row.get(f"semantic_score_{suffix}", 0.0) or 0.0)
                raw_score = row.get(f"semantic_score_raw_{suffix}")
                weighted_score += positive_weights[view] * score
                found_any = True
                if raw_score is not None:
                    raw_components.append(float(raw_score))
        row["semantic_score"] = float(weighted_score)
        row["semantic_score_raw"] = float(np.mean(raw_components)) if raw_components else None
        row["semantic_embedding_found"] = bool(found_any)
        if found_any:
            found_any_count += 1
            combined_scores.append(float(weighted_score))

    diagnostics["candidate_embedding_found_count"] = found_any_count
    diagnostics["candidate_embedding_missing_count"] = len(scored_rows) - found_any_count
    if per_view_found_sets:
        union_found = set().union(*per_view_found_sets)
        diagnostics["missing_candidate_item_ids"] = [
            row.get("item_id") for index, row in enumerate(scored_rows) if index not in union_found
        ][:50]
    else:
        diagnostics["missing_candidate_item_ids"] = []
    diagnostics["missing_candidate_item_ids_by_view"] = {
        view: values[:50] for view, values in missing_by_view.items()
    }

    if combined_scores:
        scores = np.asarray(combined_scores, dtype=np.float32)
        diagnostics["semantic_score_min"] = float(np.min(scores))
        diagnostics["semantic_score_mean"] = float(np.mean(scores))
        diagnostics["semantic_score_max"] = float(np.max(scores))
        diagnostics["semantic_score_std"] = float(np.std(scores))

    _assign_semantic_ranks(scored_rows)
    return scored_rows, diagnostics


def _assign_semantic_ranks(
    scored_rows: list[dict[str, Any]],
    score_field: str = "semantic_score",
    found_field: str = "semantic_embedding_found",
    rank_field: str = "semantic_rank",
) -> None:
    valid = [
        (index, float(row[score_field]))
        for index, row in enumerate(scored_rows)
        if row.get(found_field)
    ]
    missing = [
        index for index, row in enumerate(scored_rows) if not row.get(found_field)
    ]
    ordered_valid = sorted(valid, key=lambda pair: (-pair[1], pair[0]))

    rank = 1
    for index, _score in ordered_valid:
        scored_rows[index][rank_field] = rank
        rank += 1
    for index in missing:
        scored_rows[index][rank_field] = rank
        rank += 1


def _view_suffix(view: str) -> str:
    if view == "visit_pattern":
        return "visit"
    if view == "category_context":
        return "category"
    return str(view)


def _safe_int(value) -> int | None:
    if value is None:
        return None
    return int(value)
