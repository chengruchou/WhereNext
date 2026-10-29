"""Example contract instances for UI mocks and schema checks.

The POIs, coordinates, counts and distances are real Gowalla records from
datasets/filtered_poi_metadata.json (Austin, the user in the paper's Figure 2).
Signal values, weights and latencies are hand-written, not model output.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from .evidence import (
    EvidenceRecord,
    ExplanationSentence,
    GroundedExplanation,
    HistoryRelation,
    IntentMatch,
    PoiFacts,
    RouteEvidence,
    Signal,
    SignalGap,
    StageStatus,
    StepExplanation,
    TravelLeg,
    WhyNotEvidence,
    resolve_ref,
)
from .intent import (
    CategoryMatch,
    Intent,
    IntentPhrase,
    ParsedIntent,
    ParserTrace,
    SteeringControls,
)


QUERY = "Something cultural before dinner, within walking distance. Open late would be nice."
# final = (1 - lambda) * (0.9 * habit + 0.1 * geo) + lambda * intent + epsilon * novelty,
# with lambda = 0.6 and epsilon = 0.15 (EXAMPLE_CONTROLS) and the default spatial weights.
WEIGHTS = {"habit": 0.4 * 0.9, "geo": 0.4 * 0.1, "intent": 0.6, "novelty": 0.15}

EXAMPLE_PARSED_INTENT = ParsedIntent(
    want=[
        IntentPhrase(
            phrase="something cultural",
            category_hints=["Museum", "Historic Landmark", "Theatre", "Gallery"],
        ),
        IntentPhrase(phrase="dinner", category_hints=["Middle Eastern", "French", "American"]),
    ],
    strength="soft",
    explore="new",
    max_hop_km=1.0,
    travel_mode="walk",
    unsupported=["open late"],
)

EXAMPLE_INTENT = Intent(
    query=QUERY,
    source="llm",
    want=[
        CategoryMatch(category_name="Museum", phrase="something cultural", method="llm_hint"),
        CategoryMatch(
            category_name="Historic Landmark", phrase="something cultural", method="llm_hint"
        ),
        CategoryMatch(category_name="Middle Eastern", phrase="dinner", method="llm_hint"),
    ],
    strength="soft",
    explore="new",
    max_hop_km=1.0,
    travel_mode="walk",
    unsupported=["open late"],
    parser=ParserTrace(model="gemini-2.5-flash", latency_ms=850.0, fallback=False),
)

EXAMPLE_CONTROLS = SteeringControls(habit_intent=0.6, explore=0.15, source="intent")


def _signals(raw: dict[str, float | None], values: dict[str, float]) -> dict[str, Signal]:
    return {
        name: Signal(
            raw=raw.get(name),
            value=value,
            weight=WEIGHTS[name],
            contribution=WEIGHTS[name] * value,
        )
        for name, value in values.items()
    }


def _record(**fields: Any) -> EvidenceRecord:
    signals = fields["signals"]
    contributions = {name: signal.contribution for name, signal in signals.items()}
    return EvidenceRecord(
        final_score=sum(contributions.values()),
        top_signal=max(contributions, key=contributions.__getitem__),
        **fields,
    )


def _coffee_history(window: int = 3) -> HistoryRelation:
    return HistoryRelation(history_window=window, same_category_visits=0, visited_this_poi=False)


HISTORY = [
    PoiFacts(
        raw_poi_id=18417,
        category_name="Coffee Shop",
        latitude=30.2448597206,
        longitude=-97.7571630478,
        checkins_count=1647,
        users_count=287,
        photos_count=77,
    ),
    PoiFacts(
        raw_poi_id=15326,
        category_name="Coffee Shop",
        latitude=30.2510462058,
        longitude=-97.7493242919,
        checkins_count=1675,
        users_count=874,
        photos_count=124,
    ),
    PoiFacts(
        raw_poi_id=480992,
        category_name="Coffee Shop",
        latitude=30.26485415,
        longitude=-97.7438453833,
        checkins_count=391,
        users_count=161,
        photos_count=23,
    ),
]
MUSEUM = PoiFacts(
    raw_poi_id=10674,
    category_name="Museum",
    latitude=30.2649400485,
    longitude=-97.7450233698,
    checkins_count=555,
    users_count=392,
    photos_count=61,
)
LANDMARK = PoiFacts(
    raw_poi_id=91215,
    category_name="Historic Landmark",
    latitude=30.26314464,
    longitude=-97.7448624372,
    checkins_count=292,
    users_count=216,
    photos_count=6,
)
MIDDLE_EASTERN = PoiFacts(
    raw_poi_id=42079,
    category_name="Middle Eastern",
    latitude=30.2678592833,
    longitude=-97.7381999667,
    checkins_count=536,
    users_count=298,
    photos_count=18,
)
COFFEE = PoiFacts(
    raw_poi_id=15245,
    category_name="Coffee Shop",
    latitude=30.2642977167,
    longitude=-97.73298025,
    checkins_count=1986,
    users_count=755,
    photos_count=76,
)

STEP_1 = _record(
    step=1,
    rank=1,
    pool_size=40,
    candidate_source="sbr+spatial",
    poi=MUSEUM,
    signals=_signals(
        {"geo": 0.114},
        {"habit": 0.42, "intent": 1.0, "geo": 1 / 1.114, "novelty": 1.0},
    ),
    travel=TravelLeg(from_raw_poi_id=480992, distance_km=0.114, mode="walk"),
    intent=IntentMatch(matched_want=["Museum"]),
    history=_coffee_history(),
)
STEP_2 = _record(
    step=2,
    rank=1,
    pool_size=40,
    candidate_source="spatial",
    poi=LANDMARK,
    signals=_signals(
        {"geo": 0.2},
        {"habit": 0.0, "intent": 1.0, "geo": 1 / 1.2, "novelty": 1.0},
    ),
    travel=TravelLeg(from_raw_poi_id=10674, distance_km=0.2, mode="walk"),
    intent=IntentMatch(matched_want=["Historic Landmark"]),
    history=_coffee_history(window=4),
)
STEP_3 = _record(
    step=3,
    rank=1,
    pool_size=40,
    candidate_source="sbr",
    poi=MIDDLE_EASTERN,
    signals=_signals(
        {"geo": 0.827},
        {"habit": 0.80, "intent": 1.0, "geo": 1 / 1.827, "novelty": 1.0},
    ),
    travel=TravelLeg(from_raw_poi_id=91215, distance_km=0.827, mode="walk"),
    intent=IntentMatch(matched_want=["Middle Eastern"]),
    history=_coffee_history(window=5),
)

EXAMPLE_ROUTE_EVIDENCE = RouteEvidence(
    request_id="example-0001",
    user_id=123,
    dataset="gowalla",
    backbone="MG-DSGAT",
    history=HISTORY,
    intent=EXAMPLE_INTENT,
    controls=EXAMPLE_CONTROLS,
    steps=[STEP_1, STEP_2, STEP_3],
    stages=[
        StageStatus(stage="intent_parse", status="ran", latency_ms=850.0),
        StageStatus(stage="sbr", status="ran", latency_ms=38.0),
        StageStatus(stage="spatial", status="ran", latency_ms=4.0),
        StageStatus(
            stage="semantic",
            status="skipped",
            detail="embedding file not found: poi_semantic_embeddings.pt",
        ),
        StageStatus(
            stage="intent_score",
            status="ran",
            latency_ms=12.0,
            detail="lambda=0.6; epsilon=0.15; 20 intent candidates added",
        ),
    ],
)

_ASKED_COFFEE = _record(
    step=1,
    rank=9,
    pool_size=40,
    candidate_source="sbr",
    poi=COFFEE,
    signals=_signals(
        {"geo": 1.045},
        {"habit": 0.95, "intent": 0.0, "geo": 1 / 2.045, "novelty": 0.0},
    ),
    travel=TravelLeg(from_raw_poi_id=480992, distance_km=1.045, mode="walk"),
    intent=IntentMatch(within_budget=False),
    history=HistoryRelation(
        history_window=3, same_category_visits=3, visited_this_poi=False, steps_since_category=1
    ),
)

EXAMPLE_WHY_NOT = WhyNotEvidence(
    step=1,
    asked=COFFEE,
    asked_record=_ASKED_COFFEE,
    chosen_raw_poi_id=MUSEUM.raw_poi_id,
    reasons=["over_hop_distance", "repeated_category"],
    gaps=[
        SignalGap(
            signal=name,
            asked=_ASKED_COFFEE.signals[name].contribution,
            chosen=STEP_1.signals[name].contribution,
            gap=STEP_1.signals[name].contribution - _ASKED_COFFEE.signals[name].contribution,
        )
        for name in WEIGHTS
    ],
)

EXAMPLE_EXPLANATION = GroundedExplanation(
    summary=[
        ExplanationSentence(
            text="Your last three visits were coffee shops, and none of the three stops "
            "repeats that category.",
            evidence_refs=[
                "history[0].category_name",
                "history[1].category_name",
                "history[2].category_name",
                "steps[0].history.same_category_visits",
                "steps[1].history.same_category_visits",
                "steps[2].history.same_category_visits",
            ],
        )
    ],
    steps=[
        StepExplanation(
            step=1,
            sentences=[
                ExplanationSentence(
                    text="The museum is 0.11 km from your last coffee stop and matches "
                    "'something cultural'.",
                    evidence_refs=[
                        "steps[0].travel.distance_km",
                        "steps[0].travel.from_raw_poi_id",
                        "history[2].raw_poi_id",
                        "history[2].category_name",
                        "steps[0].intent.matched_want",
                    ],
                )
            ],
        ),
        StepExplanation(
            step=3,
            sentences=[
                ExplanationSentence(
                    text="Middle Eastern covers dinner, and it is the stop your past visits "
                    "support most.",
                    evidence_refs=[
                        "steps[2].intent.matched_want",
                        "steps[0].signals.habit.value",
                        "steps[1].signals.habit.value",
                        "steps[2].signals.habit.value",
                    ],
                )
            ],
        ),
    ],
)


def run_contracts_smoke_test() -> dict[str, Any]:
    """Round-trip every example and check that explanation refs resolve."""

    evidence_json = EXAMPLE_ROUTE_EVIDENCE.model_dump(mode="json")
    sentences = list(EXAMPLE_EXPLANATION.summary)
    for step in EXAMPLE_EXPLANATION.steps:
        sentences.extend(step.sentences)
    refs = [ref for sentence in sentences for ref in sentence.evidence_refs]
    resolved = {ref: resolve_ref(evidence_json, ref) for ref in refs}

    round_trips = {
        "parsed_intent": ParsedIntent.model_validate_json(EXAMPLE_PARSED_INTENT.model_dump_json()),
        "intent": Intent.model_validate_json(EXAMPLE_INTENT.model_dump_json()),
        "route_evidence": RouteEvidence.model_validate_json(
            EXAMPLE_ROUTE_EVIDENCE.model_dump_json()
        ),
        "why_not": WhyNotEvidence.model_validate_json(EXAMPLE_WHY_NOT.model_dump_json()),
        "explanation": GroundedExplanation.model_validate_json(
            EXAMPLE_EXPLANATION.model_dump_json()
        ),
    }

    rejected: dict[str, str] = {}
    bad_record = STEP_1.model_dump()
    bad_record["final_score"] += 0.1
    bad_unknown_field = EXAMPLE_PARSED_INTENT.model_dump() | {"rating": 4.5}
    for name, model, payload in (
        ("score_not_decomposed", EvidenceRecord, bad_record),
        ("unknown_field", ParsedIntent, bad_unknown_field),
    ):
        try:
            model.model_validate(payload)
        except ValidationError as exc:
            rejected[name] = exc.errors()[0]["msg"]

    try:
        resolve_ref(evidence_json, "steps[0].poi.rating")
    except KeyError:
        rejected["missing_ref"] = "steps[0].poi.rating"

    return {
        "round_trips": sorted(round_trips),
        "resolved_refs": resolved,
        "rejected": rejected,
        "step_scores": {
            record.poi.category_name: round(record.final_score, 4)
            for record in EXAMPLE_ROUTE_EVIDENCE.steps
        },
        "why_not_reasons": EXAMPLE_WHY_NOT.reasons,
    }


if __name__ == "__main__":
    print(json.dumps(run_contracts_smoke_test(), indent=2))
