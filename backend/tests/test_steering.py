"""Steering: request similarity stays inside the evidence schema's bounds, and an unmet
request keeps its stops within reach."""

import dataclasses

from contracts.intent import CategoryMatch, Intent, SteeringControls
from services.evidence_builder import _intent_match
from services.model_config import RecommendationConfig
from services.steering import PoiIndex, PoiPoint, steer


def test_similarity_rounding_above_one_is_clamped():
    index = PoiIndex([
        PoiPoint(raw_id=1, lat=30.2672, lng=-97.7431, category="Coffee Shop"),
        PoiPoint(raw_id=2, lat=30.2680, lng=-97.7420, category="Museum"),
        PoiPoint(raw_id=3, lat=30.2690, lng=-97.7410, category="Museum"),
    ])
    intent = Intent(
        query="a museum",
        source="user_edit",
        want=[CategoryMatch(category_name="Museum", phrase="museum", method="user_edit")],
    )
    rows = [{"raw_poi_id": 2, "normalized_sbr_score": 0.5, "spatial_score": 0.9},
            {"raw_poi_id": 3, "normalized_sbr_score": 0.4, "spatial_score": 0.8}]
    steered, _ = steer(
        rows,
        intent=intent,
        controls=SteeringControls(habit_intent=0.5, explore=0.1, source="intent"),
        session_ids=[1],
        index=index,
        raw2item={},
        config=RecommendationConfig.from_env(),
        spatial_ran=False,
        intent_scores={"Museum": (1.0, 1.0000001192092896)},  # float32 cosine of a match
    )
    assert steered
    for row in steered:
        assert -1.0 <= row["intent_similarity"] <= 1.0
        assert _intent_match(row) is not None  # validates against the schema


# Austin: a coffee shop, a bar 0.5 km away and a bar 30 km away; no museum anywhere.
UNMET_INDEX = PoiIndex([
    PoiPoint(raw_id=1, lat=30.2672, lng=-97.7431, category="Coffee Shop"),
    PoiPoint(raw_id=2, lat=30.2700, lng=-97.7400, category="Bar"),
    PoiPoint(raw_id=3, lat=30.5300, lng=-97.7431, category="Bar"),
])
MUSEUM_ON_FOOT = Intent(
    query="a museum on foot",
    source="user_edit",
    travel_mode="walk",
    want=[CategoryMatch(category_name="Museum", phrase="museum", method="user_edit")],
)


def steer_unmet(rows, config):
    steered, summary = steer(
        rows,
        intent=MUSEUM_ON_FOOT,
        controls=SteeringControls(habit_intent=0.5, explore=0.1, source="intent"),
        session_ids=[1],
        index=UNMET_INDEX,
        raw2item={},
        config=config,
        spatial_ran=False,
    )
    return [int(row["raw_poi_id"]) for row in steered], summary


def test_unmet_request_keeps_stops_within_reach():
    # Habit prefers the far bar; with nothing wanted in reach, the near one is still chosen.
    rows = [{"raw_poi_id": 3, "normalized_sbr_score": 1.0, "spatial_score": 0.0},
            {"raw_poi_id": 2, "normalized_sbr_score": 0.1, "spatial_score": 0.6}]
    ids, summary = steer_unmet(rows, RecommendationConfig.from_env())
    assert ids == [2]
    assert "beyond 2 km removed" in summary


def test_unmet_request_falls_back_to_the_nearest_when_none_is_in_reach():
    rows = [{"raw_poi_id": 3, "normalized_sbr_score": 1.0, "spatial_score": 0.0}]
    ids, _ = steer_unmet(rows, RecommendationConfig.from_env())
    assert ids == [3]


def test_the_old_behaviour_is_still_available():
    rows = [{"raw_poi_id": 3, "normalized_sbr_score": 1.0, "spatial_score": 0.0},
            {"raw_poi_id": 2, "normalized_sbr_score": 0.1, "spatial_score": 0.6}]
    config = dataclasses.replace(RecommendationConfig.from_env(), intent_unmet_within_reach=False)
    ids, _ = steer_unmet(rows, config)
    assert set(ids) == {2, 3}
