"""Route costs for multi-stop routes: travel distance and repeated categories.

final = prior - beta * travel - mu * repeat

prior is the score the row already had (pipeline, plus intent steering when it
ran). travel is the hop from the previous stop over the route's distance scale,
capped at 1; the scale is the request's max_hop_km, else the reach of its travel
mode, and route_travel_scale_km without a request.
repeat is 1 when the POI's category already appears earlier in this route.
Unlike the pipeline's own distance signal, these costs do not shrink as lambda
grows, so a firm request still prefers the nearer of two fitting places.
"""

from __future__ import annotations

from typing import Any

from contracts.intent import Intent, SteeringControls
from services.evidence_builder import haversine_km, normalized_sbr_by_raw_id, step_signals
from services.model_config import RecommendationConfig
from services.steering import PoiIndex


def route_planning_enabled(config: RecommendationConfig) -> bool:
    return config.route_repeat_penalty > 0 or config.route_travel_weight > 0


def plan_step(
    rows: list[dict[str, Any]],
    *,
    route_stops: list[int],
    session_ids: list[int],
    index: PoiIndex,
    config: RecommendationConfig,
    intent: Intent | None,
    controls: SteeringControls,
) -> tuple[list[dict[str, Any]], str]:
    """Return the pool re-ranked with route costs, and a summary for the stage status."""

    origin = index.points.get(session_ids[-1]) if session_ids else None
    route_categories = {
        index.points[raw_id].category for raw_id in route_stops if raw_id in index.points
    }
    if intent is not None:
        scale = intent.max_hop_km or config.reach_km(intent.travel_mode)
    else:
        scale = config.route_travel_scale_km
    mu, beta = config.route_repeat_penalty, config.route_travel_weight

    planned = [dict(row) for row in rows]
    # Pin the SBR normalization to this pool so the evidence decomposes the same numbers.
    fallback_habit = normalized_sbr_by_raw_id(rows)
    repeats = 0
    for row in planned:
        raw_id = int(row["raw_poi_id"])
        if row.get("normalized_sbr_score") is None and row.get("sbr_score") is not None:
            row["normalized_sbr_score"] = fallback_habit.get(raw_id, 0.0)
        point = index.points.get(raw_id)
        if row.get("hop_km") is None and origin is not None and point is not None:
            row["hop_km"] = haversine_km(origin.lat, origin.lng, point.lat, point.lng)
        travel = min(row["hop_km"] / scale, 1.0) if row.get("hop_km") is not None else 0.0
        repeat = 1.0 if point is not None and point.category in route_categories else 0.0
        repeats += int(repeat)
        prior = sum(s.contribution for s in step_signals(row, config, {}, controls).values())
        row["travel_value"] = -travel if travel else 0.0  # avoid a printed "-0.0"
        row["repeat_value"] = -repeat if repeat else 0.0
        row["route_prior_score"] = prior
        row["route_score"] = prior - beta * travel - mu * repeat

    planned.sort(
        key=lambda row: (
            -row["route_score"],
            -row["route_prior_score"],
            row.get("hop_km", float("inf")),
            int(row["raw_poi_id"]),
        )
    )
    for rank, row in enumerate(planned, start=1):
        row["rank"] = rank

    parts = [f"repeat penalty={mu:g}", f"travel weight={beta:g} per {scale:g} km"]
    if repeats:
        parts.append(f"{repeats} candidates repeat a route category")
    if origin is None:
        parts.append("no origin coordinates; travel cost not applied")
    return planned, "; ".join(parts)
