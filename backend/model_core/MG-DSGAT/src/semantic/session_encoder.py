"""Session-level semantic embedding construction from POI embeddings."""

from __future__ import annotations

from typing import Any

import numpy as np


def last_n_history_item_ids(history_item_ids: list[int], last_n: int = 20) -> list[int]:
    """Return the final N history item IDs while preserving chronological order."""

    history = [int(item_id) for item_id in history_item_ids]
    if last_n <= 0:
        return history
    return history[-int(last_n) :]


def mean_pool_history_embeddings(
    history_item_ids,
    embedding_store,
    last_n: int = 20,
    view: str | None = None,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Mean-pool available POI embeddings from the session history."""

    selected_ids = last_n_history_item_ids(list(history_item_ids or []), last_n=last_n)
    return _pool_history_embeddings(
        history_item_ids=list(history_item_ids or []),
        selected_ids=selected_ids,
        embedding_store=embedding_store,
        strategy="mean",
        weights=None,
        view=view,
    )


def recency_weighted_pool_history_embeddings(
    history_item_ids,
    embedding_store,
    last_n: int = 20,
    decay: float = 0.85,
    view: str | None = None,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Pool history embeddings with exponentially larger weights for recent POIs."""

    selected_ids = last_n_history_item_ids(list(history_item_ids or []), last_n=last_n)
    selected_len = len(selected_ids)
    if selected_len == 0:
        weights = np.asarray([], dtype=np.float32)
    else:
        decay = float(decay)
        weights = np.asarray(
            [decay ** (selected_len - index - 1) for index in range(selected_len)],
            dtype=np.float32,
        )
    return _pool_history_embeddings(
        history_item_ids=list(history_item_ids or []),
        selected_ids=selected_ids,
        embedding_store=embedding_store,
        strategy="recency_weighted",
        weights=weights,
        view=view,
        extra_diagnostics={"decay": float(decay)},
    )


def build_session_embedding(
    history_item_ids,
    embedding_store,
    strategy: str = "recency_weighted",
    last_n: int = 20,
    decay: float = 0.85,
    view: str | None = None,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Build a normalized semantic embedding for a session history."""

    strategy_normalized = str(strategy).lower()
    if strategy_normalized == "mean":
        return mean_pool_history_embeddings(history_item_ids, embedding_store, last_n=0, view=view)
    if strategy_normalized == "last_n_mean":
        embedding, diagnostics = mean_pool_history_embeddings(
            history_item_ids,
            embedding_store,
            last_n=last_n,
            view=view,
        )
        diagnostics["strategy"] = "last_n_mean"
        return embedding, diagnostics
    if strategy_normalized == "recency_weighted":
        return recency_weighted_pool_history_embeddings(
            history_item_ids,
            embedding_store,
            last_n=last_n,
            decay=decay,
            view=view,
        )
    raise ValueError(
        "Unsupported session semantic embedding strategy. "
        "Expected one of: mean, recency_weighted, last_n_mean."
    )


def build_multi_view_session_embeddings(
    history_item_ids,
    embedding_store,
    views: list[str] | tuple[str, ...],
    strategy: str = "recency_weighted",
    last_n: int = 20,
    decay: float = 0.85,
) -> tuple[dict[str, np.ndarray | None], dict[str, Any]]:
    """Build one normalized session embedding per semantic view."""

    embeddings_by_view: dict[str, np.ndarray | None] = {}
    diagnostics_by_view: dict[str, Any] = {}
    for view in views:
        embedding, diagnostics = build_session_embedding(
            history_item_ids,
            embedding_store,
            strategy=strategy,
            last_n=last_n,
            decay=decay,
            view=str(view),
        )
        diagnostics["view"] = str(view)
        embeddings_by_view[str(view)] = embedding
        diagnostics_by_view[str(view)] = diagnostics
    return embeddings_by_view, diagnostics_by_view


def _pool_history_embeddings(
    history_item_ids: list[int],
    selected_ids: list[int],
    embedding_store,
    strategy: str,
    weights: np.ndarray | None,
    view: str | None = None,
    extra_diagnostics: dict[str, Any] | None = None,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "strategy": strategy,
        "original_history_length": len(history_item_ids),
        "used_history_length": len(selected_ids),
        "found_embedding_count": 0,
        "missing_embedding_count": 0,
        "missing_item_ids": [],
        "session_embedding_norm": None,
        "status": "ok",
        "view": view,
    }
    if extra_diagnostics:
        diagnostics.update(extra_diagnostics)

    if not selected_ids:
        diagnostics["status"] = "empty_history"
        return None, diagnostics

    found_embeddings = []
    found_weights = []
    for index, item_id in enumerate(selected_ids):
        item_id = int(item_id)
        if embedding_store.has_item_id(item_id, view=view):
            found_embeddings.append(
                np.asarray(embedding_store.get_by_item_id(item_id, view=view), dtype=np.float32)
            )
            if weights is not None:
                found_weights.append(float(weights[index]))
        else:
            diagnostics["missing_item_ids"].append(item_id)

    diagnostics["found_embedding_count"] = len(found_embeddings)
    diagnostics["missing_embedding_count"] = len(diagnostics["missing_item_ids"])

    if not found_embeddings:
        diagnostics["status"] = "no_embeddings_found"
        return None, diagnostics

    matrix = np.vstack(found_embeddings).astype(np.float32)
    if weights is None:
        pooled = np.mean(matrix, axis=0)
    else:
        weight_array = np.asarray(found_weights, dtype=np.float32)
        weight_sum = float(np.sum(weight_array))
        if weight_sum <= 0.0:
            pooled = np.mean(matrix, axis=0)
        else:
            pooled = np.average(matrix, axis=0, weights=weight_array)

    pooled = _normalize_vector(pooled)
    diagnostics["session_embedding_norm"] = (
        float(np.linalg.norm(pooled)) if pooled is not None else None
    )
    diagnostics["missing_item_ids"] = diagnostics["missing_item_ids"][:50]
    return pooled, diagnostics


def _normalize_vector(vector: np.ndarray) -> np.ndarray | None:
    vector = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if norm <= 0.0:
        return None
    return (vector / norm).astype(np.float32)
