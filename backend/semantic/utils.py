"""Utilities for semantic reranking."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def describe_count_band(value: float | None) -> str:
    """Turn a numeric value into a compact semantic descriptor."""

    if value is None:
        return "unknown"
    if value < 1:
        return "very low"
    if value < 10:
        return "low"
    if value < 100:
        return "moderate"
    if value < 1000:
        return "high"
    return "very high"


def infer_usage_tendency(poi_metadata: dict[str, Any]) -> str:
    """Infer coarse usage tendency from available engagement metadata."""

    category = (poi_metadata.get("category_name") or "").lower()
    checkins = safe_float(poi_metadata.get("checkins_count")) or 0.0
    users = safe_float(poi_metadata.get("users_count")) or 0.0
    events = safe_float(poi_metadata.get("checkins_count_from_events")) or 0.0

    if any(keyword in category for keyword in ["coffee", "cafe", "restaurant", "bar", "food"]):
        return "repeat casual visits and social gathering"
    if any(keyword in category for keyword in ["office", "hall", "school", "university", "airport"]):
        return "purpose-driven visits with functional intent"
    if checkins > 1000 or users > 500:
        return "high-traffic destination with broad appeal"
    if events > 100:
        return "event-driven visits with periodic surges"
    return "general local visitation pattern"


def simple_region_summary(lat: float | None, lng: float | None) -> str:
    """Create a simple region-like descriptor from coordinates."""

    if lat is None or lng is None:
        return "unknown region"

    lat_band = f"{abs(lat):.1f} degrees {'north' if lat >= 0 else 'south'}"
    lng_band = f"{abs(lng):.1f} degrees {'east' if lng >= 0 else 'west'}"

    coarse_lat = math.floor(lat / 5.0) * 5
    coarse_lng = math.floor(lng / 5.0) * 5
    grid = f"coarse geo-cell ({coarse_lat},{coarse_lng})"
    return f"{lat_band}, {lng_band}, {grid}"


def get_category_descriptors(poi_metadata: dict[str, Any]) -> str:
    """Extract semantic category descriptors with safe fallbacks."""

    raw_categories = poi_metadata.get("raw_categories") or []
    names = []
    for entry in raw_categories:
        name = (entry or {}).get("name")
        if name:
            names.append(str(name))

    primary = poi_metadata.get("category_name")
    if primary and primary not in names:
        names.insert(0, str(primary))

    if not names:
        return "no detailed category descriptors available"
    return ", ".join(dict.fromkeys(names))


def min_max_normalize(values: list[float]) -> list[float]:
    """Normalize values into [0, 1] with a stable equal-values fallback."""

    if not values:
        return []

    arr = np.asarray(values, dtype=np.float32)
    min_val = float(np.min(arr))
    max_val = float(np.max(arr))
    if max_val - min_val < 1e-12:
        return [1.0 for _ in values]
    normalized = (arr - min_val) / (max_val - min_val)
    return normalized.astype(np.float32).tolist()


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    """Compute cosine similarity with zero-vector safety."""

    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def average_vectors(vectors: list[np.ndarray]) -> np.ndarray | None:
    """Average vectors and return a unit-normalized result."""

    if not vectors:
        return None
    stacked = np.vstack(vectors)
    avg = np.mean(stacked, axis=0)
    norm = np.linalg.norm(avg)
    return avg if norm == 0 else avg / norm


def rank_predictions_by_raw_id(predictions: list[dict[str, Any]]) -> list[int]:
    """Return raw ids in their current prediction order."""

    return [int(pred["raw_location_id"]) for pred in predictions if "raw_location_id" in pred]


def run_mock_rerank_demo() -> dict[str, Any]:
    """Tiny debug/demo helper for local sanity checks."""

    from .reranker import rerank_packaged_candidates
    from .schemas import CandidatePOI

    candidates = [
        CandidatePOI(
            rank=1,
            item_id=1,
            score=0.90,
            raw_location_id=101,
            poi_metadata={"raw_poi_id": 101, "category_name": "Coffee Shop", "checkins_count": 500, "users_count": 120, "latitude": 25.03, "longitude": 121.56},
        ),
        CandidatePOI(
            rank=2,
            item_id=2,
            score=0.85,
            raw_location_id=102,
            poi_metadata={"raw_poi_id": 102, "category_name": "City Hall", "checkins_count": 200, "users_count": 80, "latitude": 25.04, "longitude": 121.53},
        ),
    ]
    history_metadata = [
        {"raw_poi_id": 201, "category_name": "Coffee Shop", "checkins_count": 400, "users_count": 100, "latitude": 25.05, "longitude": 121.55}
    ]
    return rerank_packaged_candidates(user_id=999, candidates=candidates, history_poi_metadata=history_metadata)

