"""Steer the ranked candidate pool with a parsed intent.

final = (1 - lambda) * base + lambda * intent + epsilon * novelty

base is the score the pipeline already ranked by (SBR, spatial and semantic
fusion), so lambda = epsilon = 0 reproduces the pipeline's order. intent is the
graded relevance of the POI's category to the wanted phrases (intent_signal.py);
without scores it falls back to 1 for a wanted category and 0 otherwise.
novelty is 1 minus the share of the user's trajectory spent in the POI's
category. Before scoring, POIs in avoided categories or beyond max_hop_km are
removed, and the nearest POIs in the wanted categories join the pool, since the
backbone may propose none of them. When places of the wanted categories are within
reach (max_hop_km, else the reach of the travel mode), only they are kept, so the
request decides the stop and the score ranks within it; with none in reach, the
request scores nothing and habit (plus novelty, when asked for) decides.

Within the request, every kept place gets the same two base signals: habit, the
sequence model's score for it after this session, normalized over the kept places,
and closeness to the previous stop. Places that joined only through the request have
no score from the backbone's top-K list, so without this they would be ordered by
distance alone.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contracts.intent import Intent, SteeringControls

from services.evidence_builder import base_signals, haversine_km, normalized_sbr_by_raw_id
from services.intent_signal import IntentScores
from services.model_config import RecommendationConfig

# Candidates habit may rank when a request cannot be met and none is within reach.
UNMET_NEAREST = 5


@dataclass(frozen=True)
class PoiPoint:
    raw_id: int
    lat: float
    lng: float
    category: str | None


class PoiIndex:
    """Coordinates and categories of every POI in the metadata, grouped by category."""

    def __init__(self, points: list[PoiPoint]):
        self.points = {point.raw_id: point for point in points}
        self.by_category: dict[str, list[PoiPoint]] = {}
        for point in points:
            if point.category:
                self.by_category.setdefault(point.category, []).append(point)

    @classmethod
    def from_metadata(cls, path: Path) -> PoiIndex:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = payload.values() if isinstance(payload, dict) else payload
        return cls(
            [
                PoiPoint(
                    raw_id=int(row["raw_poi_id"]),
                    lat=float(row["latitude"]),
                    lng=float(row["longitude"]),
                    category=row.get("category_name") or None,
                )
                for row in rows
            ]
        )

    def nearest_in_categories(
        self,
        categories: list[str],
        origin: PoiPoint,
        k: int,
        radius_km: float,
        exclude: set[int],
    ) -> list[tuple[float, PoiPoint]]:
        found = []
        for category in dict.fromkeys(categories):
            for point in self.by_category.get(category, []):
                if point.raw_id in exclude:
                    continue
                distance = haversine_km(origin.lat, origin.lng, point.lat, point.lng)
                if distance <= radius_km:
                    found.append((distance, point))
        found.sort(key=lambda item: (item[0], item[1].raw_id))
        return found[:k]


def needs_steering(intent: Intent | None, controls: SteeringControls) -> bool:
    return intent is not None or controls.habit_intent > 0 or controls.explore > 0


def steer(
    rows: list[dict[str, Any]],
    *,
    intent: Intent | None,
    controls: SteeringControls,
    session_ids: list[int],
    index: PoiIndex,
    raw2item: dict[int, int],
    config: RecommendationConfig,
    spatial_ran: bool,
    intent_scores: IntentScores | None = None,
    signal_method: str = "category match",
    habit_scores: Callable[[list[int]], dict[int, float]] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Return the re-ranked pool and a one-line summary for the stage status.

    intent_scores maps category name to (value, raw similarity); None means a
    binary category match. habit_scores returns the sequence model's score for each
    given raw POI ID; None, or an empty answer, leaves habit as the pipeline set it.
    """

    origin = index.points.get(session_ids[-1]) if session_ids else None
    want = [match.category_name for match in intent.want] if intent else []
    avoid = {match.category_name for match in intent.avoid} if intent else set()
    max_hop_km = intent.max_hop_km if intent else None
    lam, eps = controls.habit_intent, controls.explore

    pool = [dict(row) for row in rows]
    radius_km = max_hop_km or config.reach_km(intent.travel_mode if intent else "drive")
    visited = set(session_ids) if config.exclude_seen else set()
    # How many places of the wanted types the data has within reach; 0 lets the UI say
    # the request could not be met here, rather than that it lost to habit.
    in_range = None
    if want and origin is not None:
        in_range = len(
            index.nearest_in_categories(
                want, origin, k=len(index.points), radius_km=radius_km, exclude=visited
            )
        )
    added = 0
    if want and lam > 0 and origin is not None and config.intent_k > 0:
        exclude = {int(row["raw_poi_id"]) for row in pool} | visited
        nearest = index.nearest_in_categories(
            want,
            origin,
            k=config.intent_k,
            radius_km=radius_km,
            exclude=exclude,
        )
        for distance, point in nearest:
            spatial_score = 1.0 / (1.0 + distance)
            row = {
                "raw_poi_id": point.raw_id,
                "raw_location_id": point.raw_id,
                "item_id": raw2item.get(point.raw_id),
                "candidate_source": "intent",
                "sbr_score": None,
                "normalized_sbr_score": 0.0,
                "spatial_score": spatial_score,
                "distance_km": distance,
            }
            if spatial_ran:
                # Same formula the spatial stage applies to its neighbors.
                row["spatial_fusion_score"] = float(config.alpha_spatial) * spatial_score
            pool.append(row)
            added += 1

    kept = []
    avoided = too_far = 0
    for row in pool:
        point = index.points.get(int(row["raw_poi_id"]))
        category = point.category if point else None
        if category in avoid:
            avoided += 1
            continue
        if origin is not None and point is not None:
            row["hop_km"] = haversine_km(origin.lat, origin.lng, point.lat, point.lng)
            if max_hop_km is not None and row["hop_km"] > max_hop_km:
                too_far += 1
                continue
        row["category_name"] = category
        kept.append(row)

    # The request decides the stop whenever the data has a fitting place within reach.
    off_request = 0
    filtered = False
    if want and lam > 0 and config.intent_filter and in_range:
        wanted = [
            row
            for row in kept
            if row["category_name"] in want and row.get("hop_km", 0.0) <= radius_km
        ]
        if wanted:
            off_request = len(kept) - len(wanted)
            kept = wanted
            filtered = True
    # A request the data cannot meet here still sets how far the traveler will go: habit
    # ranks the places within reach, or the nearest few when none are.
    beyond_reach = 0
    if (want and lam > 0 and config.intent_filter and config.intent_unmet_within_reach
            and in_range == 0 and origin is not None and kept):
        near = [row for row in kept if row.get("hop_km", 0.0) <= radius_km]
        if not near:
            near = sorted(kept, key=lambda row: row.get("hop_km", float("inf")))[:UNMET_NEAREST]
        beyond_reach = len(kept) - len(near)
        kept = near
    habit_scored = 0
    if filtered and habit_scores is not None and config.intent_habit_scoring:
        habit_scored = _score_within_request(kept, habit_scores, spatial_ran, config)

    # Normalize SBR scores over the pool the pipeline produced, before any removal,
    # and store them so the evidence builder decomposes the same numbers.
    fallback_habit = normalized_sbr_by_raw_id(rows)
    visits = Counter(
        index.points[raw_id].category for raw_id in session_ids if raw_id in index.points
    )
    # With nothing of the wanted types within reach, the request cannot be met here, so
    # partial similarity to it does not rank stops either: habit decides, as the UI says.
    request_unmet = config.intent_filter and in_range == 0
    for row in kept:
        if row.get("normalized_sbr_score") is None:
            row["normalized_sbr_score"] = fallback_habit.get(int(row["raw_poi_id"]), 0.0)
        base = sum(s.contribution for s in base_signals(row, config, {}).values())
        score = (1.0 - lam) * base
        if want and lam > 0:
            if intent_scores is None:
                value, raw = (1.0 if row["category_name"] in want else 0.0), None
            else:
                value, raw = intent_scores.get(row["category_name"], (0.0, None))
            if request_unmet:
                value = 0.0
            row["intent_value"] = value
            # Cosine similarity in float32 can land a hair outside [-1, 1].
            row["intent_similarity"] = None if raw is None else max(-1.0, min(1.0, raw))
            score += lam * value
        if eps > 0:
            share = visits[row["category_name"]] / len(session_ids) if session_ids else 0.0
            row["novelty_value"] = 1.0 - share
            score += eps * row["novelty_value"]
        if intent is not None:
            row["intent_matched"] = [row["category_name"]] if row["category_name"] in want else []
            row["intent_in_range"] = in_range
            row["intent_radius_km"] = radius_km if in_range is not None else None
        row["steer_base_score"] = base
        row["steer_score"] = score

    kept.sort(
        key=lambda row: (
            -row["steer_score"],
            -row["steer_base_score"],
            row.get("hop_km", float("inf")),
            int(row["raw_poi_id"]),
        )
    )
    for rank, row in enumerate(kept, start=1):
        row["rank"] = rank

    parts = [f"lambda={lam:g}", f"epsilon={eps:g}"]
    if want and lam > 0:
        parts.append(f"intent signal: {signal_method}")
    if in_range is not None:
        parts.append(f"{in_range} places of the wanted types within {radius_km:g} km")
    if added:
        parts.append(f"{added} intent candidates added")
    if avoided:
        parts.append(f"{avoided} in avoided categories removed")
    if too_far:
        parts.append(f"{too_far} beyond {max_hop_km:g} km removed")
    if off_request:
        parts.append(f"{off_request} not of the wanted types removed")
    if habit_scored:
        parts.append(f"habit scored for {habit_scored} places of the wanted types")
    if request_unmet and want and lam > 0:
        parts.append("request not met within reach; ranked by habit")
    if beyond_reach:
        parts.append(f"{beyond_reach} beyond {radius_km:g} km removed")
    if origin is None:
        parts.append("no origin coordinates; distance rules not applied")
    return kept, "; ".join(parts)


def _score_within_request(
    rows: list[dict[str, Any]],
    habit_scores: Callable[[list[int]], dict[int, float]],
    spatial_ran: bool,
    config: RecommendationConfig,
) -> int:
    """Give every kept place of the request the same base signals: the sequence model's
    score, normalized over these places, and closeness to the previous stop.
    Returns how many places the model scored; 0 leaves the rows unchanged."""

    scores = habit_scores([int(row["raw_poi_id"]) for row in rows])
    known = [scores[int(row["raw_poi_id"])] for row in rows if int(row["raw_poi_id"]) in scores]
    if not known:
        return 0
    habit = _normalize_habit(known, config.intent_habit_normalization)
    for row in rows:
        raw = scores.get(int(row["raw_poi_id"]))
        row["sbr_score"] = raw
        row["normalized_sbr_score"] = 0.0 if raw is None else habit(raw)
        # Similarity to past visits was computed only for the backbone's own candidates,
        # so it is left out here; closeness is recomputed the same way for every place.
        row["semantic_fusion_score"] = None
        if row.get("hop_km") is not None:
            row["distance_km"] = row["hop_km"]
            row["spatial_score"] = 1.0 / (1.0 + row["hop_km"])
        if spatial_ran:
            row["spatial_fusion_score"] = float(config.alpha_spatial) * float(
                row.get("spatial_score") or 0.0
            )
    return len(known)


def _normalize_habit(scores: list[float], mode: str) -> Callable[[float], float]:
    """Map a raw model score to a habit value in [0, 1], given all candidates' scores.

    minmax spans 0 to 1 whatever the model's confidence; relative is exp(s - top score), so
    the top place is 1 and the rest fall as the model grows sure; softmax is the model's
    probability renormalized over the candidates.
    """

    top = max(scores)
    if mode == "relative":
        return lambda s: math.exp(s - top)
    if mode == "softmax":
        total = sum(math.exp(s - top) for s in scores)
        return lambda s: math.exp(s - top) / total
    low = min(scores)
    if top - low < 1e-12:
        return lambda s: 1.0
    return lambda s: (s - low) / (top - low)
