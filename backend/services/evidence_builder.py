"""Build evidence records from the recommendation pipeline's candidate rows.

The pipeline nests its fusions. Spatial fusion mixes the normalized SBR score
with the spatial score; semantic fusion mixes that base score with the history
similarity, and keeps the base score alone for POIs without an embedding. The
steering stage then scales that base by (1 - lambda) and adds the intent and
novelty terms. Each record flattens this into signals with the effective
weights that applied to that row, so the contributions sum to the score the
row was ranked by.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from contracts.evidence import (
    EvidenceRecord,
    HistoryRelation,
    IntentMatch,
    PoiFacts,
    Signal,
    TravelLeg,
)
from contracts.intent import SteeringControls, TravelMode
from services.model_config import RecommendationConfig


logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0088
_TOLERANCE = 1e-6


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def poi_facts(poi: dict[str, Any]) -> PoiFacts:
    return PoiFacts(
        raw_poi_id=int(poi["raw_poi_id"]),
        category_name=poi.get("category_name") or None,
        latitude=float(poi["latitude"]),
        longitude=float(poi["longitude"]),
        checkins_count=_as_count(poi.get("checkins_count")),
        users_count=_as_count(poi.get("users_count")),
        photos_count=_as_count(poi.get("photos_count")),
    )


def build_step_records(
    ranked: list[tuple[dict[str, Any], dict[str, Any]]],
    *,
    step: int,
    pool: list[dict[str, Any]],
    session: list[dict[str, Any]],
    config: RecommendationConfig,
    controls: SteeringControls | None = None,
    travel_mode: TravelMode = "drive",
) -> list[EvidenceRecord]:
    """Build one record per returned POI.

    ranked: (pipeline row, hydrated POI) pairs in final order.
    pool: every candidate row the final ranking was taken from.
    session: hydrated POIs the recommender saw, oldest first.
    controls: the steering weights, when the steering stage ranked the pool.
    """

    fallback_habit = normalized_sbr_by_raw_id(pool)
    controls = controls or SteeringControls()
    previous = session[-1] if session else None
    records: list[EvidenceRecord] = []
    for row, poi in ranked:
        signals = step_signals(row, config, fallback_habit, controls)
        contributions = {name: signal.contribution for name, signal in signals.items()}
        final_score = sum(contributions.values())
        pipeline_score = _pipeline_score(row)
        if pipeline_score is not None and not math.isclose(
            final_score, pipeline_score, abs_tol=_TOLERANCE
        ):
            logger.warning(
                "Evidence score %.6f differs from pipeline score %.6f for POI %s",
                final_score,
                pipeline_score,
                row.get("raw_poi_id"),
            )
        records.append(
            EvidenceRecord(
                step=step,
                rank=int(row["rank"]),
                pool_size=max(1, len(pool)),
                candidate_source=row.get("candidate_source") or "sbr",
                poi=poi_facts(poi),
                final_score=final_score,
                signals=signals,
                top_signal=max(contributions, key=contributions.__getitem__),
                travel=_travel_leg(previous, poi, travel_mode),
                intent=_intent_match(row),
                history=_history_relation(poi, session),
            )
        )
    return records


def step_signals(
    row: dict[str, Any],
    config: RecommendationConfig,
    fallback_habit: dict[int, float],
    controls: SteeringControls,
) -> dict[str, Signal]:
    """Base signals, scaled by (1 - lambda) and joined by intent and novelty if steered."""

    signals = base_signals(row, config, fallback_habit)
    if row.get("steer_score") is None:
        return signals
    keep = 1.0 - controls.habit_intent
    steered = {
        name: _signal(signal.raw, signal.value, signal.weight * keep)
        for name, signal in signals.items()
    }
    if row.get("intent_value") is not None:
        steered["intent"] = _signal(
            row.get("intent_similarity"), row["intent_value"], controls.habit_intent
        )
    if row.get("novelty_value") is not None:
        steered["novelty"] = _signal(None, row["novelty_value"], controls.explore)
    return steered


def base_signals(
    row: dict[str, Any],
    config: RecommendationConfig,
    fallback_habit: dict[int, float],
) -> dict[str, Signal]:
    """The pipeline's own score (SBR, spatial and semantic fusion) as signals."""

    habit = row.get("normalized_sbr_score")
    if habit is None:
        habit = fallback_habit.get(int(row["raw_poi_id"]), 0.0)
    weights = {"habit": 1.0}
    values = {"habit": float(habit)}
    raws = {"habit": row.get("sbr_score")}

    if row.get("spatial_fusion_score") is not None:
        weights = {"habit": float(config.alpha_sbr), "geo": float(config.alpha_spatial)}
        values["geo"] = float(row.get("spatial_score") or 0.0)
        raws["geo"] = row.get("distance_km")

    if _semantic_applied(row):
        gamma = max(0.0, 1.0 - float(config.semantic_weight))
        weights = {name: gamma * weight for name, weight in weights.items()}
        weights["semantic_history"] = float(config.semantic_weight)
        values["semantic_history"] = float(row["semantic_score"])

    return {name: _signal(raws.get(name), values[name], weight) for name, weight in weights.items()}


def _signal(raw: float | None, value: float, weight: float) -> Signal:
    return Signal(raw=raw, value=value, weight=weight, contribution=weight * value)


def _intent_match(row: dict[str, Any]) -> IntentMatch | None:
    if row.get("intent_matched") is None:
        return None
    return IntentMatch(matched_want=row["intent_matched"], similarity=row.get("intent_similarity"))


def _semantic_applied(row: dict[str, Any]) -> bool:
    return (
        row.get("semantic_fusion_score") is not None
        and bool(row.get("semantic_embedding_found"))
        and row.get("semantic_score") is not None
    )


def _pipeline_score(row: dict[str, Any]) -> float | None:
    for key in ("steer_score", "semantic_fusion_score", "spatial_fusion_score"):
        if row.get(key) is not None:
            return float(row[key])
    return None


def normalized_sbr_by_raw_id(pool: list[dict[str, Any]]) -> dict[int, float]:
    scored = [
        (int(row["raw_poi_id"]), float(row["sbr_score"]))
        for row in pool
        if row.get("sbr_score") is not None
    ]
    if not scored:
        return {}
    low = min(score for _, score in scored)
    high = max(score for _, score in scored)
    if high - low < 1e-12:
        return {raw_id: 1.0 for raw_id, _ in scored}
    return {raw_id: (score - low) / (high - low) for raw_id, score in scored}


def _travel_leg(
    previous: dict[str, Any] | None,
    poi: dict[str, Any],
    mode: TravelMode,
) -> TravelLeg | None:
    if previous is None:
        return None
    return TravelLeg(
        from_raw_poi_id=int(previous["raw_poi_id"]),
        distance_km=haversine_km(
            float(previous["latitude"]),
            float(previous["longitude"]),
            float(poi["latitude"]),
            float(poi["longitude"]),
        ),
        mode=mode,
    )


def _history_relation(poi: dict[str, Any], session: list[dict[str, Any]]) -> HistoryRelation:
    category = poi.get("category_name") or None
    raw_id = int(poi["raw_poi_id"])
    same_category = [
        index
        for index, visit in enumerate(session)
        if category and visit.get("category_name") == category
    ]
    return HistoryRelation(
        history_window=len(session),
        same_category_visits=len(same_category),
        visited_this_poi=any(int(visit["raw_poi_id"]) == raw_id for visit in session),
        steps_since_category=len(session) - same_category[-1] if same_category else None,
    )


def _as_count(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
