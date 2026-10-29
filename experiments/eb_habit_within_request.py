"""E-B: once the request fixes the place type, which ranking finds the place the user went to?

Design and predictions: experiments/E-B_habit_within_request.md and, for the M6 variants and
the fresh samples, experiments/E-B2_confidence_aware_habit.md (each written before its run).

Run from the repository root, with the model files set through the WHERENEXT_* variables
(see backend/.env.example). The E-B run was:

    python experiments/eb_habit_within_request.py \
        --test-split <path>/test_with_timestamps.json --seed 7 --variants M4 M5 --out eb.json

E-B2 selection: --seed 8 --exclude-seeds 7; confirmation: --seed 9 --exclude-seeds 7 8 with
--variants limited to M4 and the chosen default.

Needs the backend's dependencies plus numpy. No external API is called.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from contracts.intent import CategoryMatch, Intent
from services.intent_parser import controls_for
from services.model_config import RecommendationConfig
from services.recommendation_service import RecommendationService
from services.steering import PoiIndex

BASELINES = ["M0 random", "M1 nearest", "M2 most check-ins", "M3 habit alone"]
# WhereNext variants and the configuration each one changes.
VARIANTS: dict[str, dict[str, Any]] = {
    "M4 WhereNext, no habit scoring": {"intent_habit_scoring": False},
    "M5 WhereNext, min-max habit": {"intent_habit_scoring": True,
                                    "intent_habit_normalization": "minmax"},
    "M6a WhereNext, relative habit": {"intent_habit_scoring": True,
                                      "intent_habit_normalization": "relative"},
    "M6b WhereNext, softmax habit": {"intent_habit_scoring": True,
                                     "intent_habit_normalization": "softmax"},
}
REACH_KM = 40.0  # the drive reach, the default travel mode
CONFIDENCE_BUCKETS = (("confidence low (<0.3)", 0.0, 0.3),
                      ("confidence medium (0.3-0.6)", 0.3, 0.6),
                      ("confidence high (>=0.6)", 0.6, 1.01))


def short(method: str) -> str:
    return method.split()[0]


def rank_of(target: int, ordered: list[int]) -> int | None:
    try:
        return ordered.index(target) + 1
    except ValueError:
        return None


def metrics_from_rank(rank: int | None) -> tuple[float, float, float]:
    """HR@1, HR@5, reciprocal rank; a missing target counts as a miss."""
    if rank is None:
        return 0.0, 0.0, 0.0
    return float(rank == 1), float(rank <= 5), 1.0 / rank


def random_expectation(n: int) -> tuple[float, float, float]:
    """Exact expected HR@1, HR@5 and reciprocal rank of a uniformly random order of n."""
    harmonic = sum(1.0 / k for k in range(1, n + 1))
    return 1.0 / n, min(5, n) / n, harmonic / n


def model_confidence(scores: list[float]) -> float | None:
    """The largest of the model's probabilities renormalized over the candidates."""
    if not scores:
        return None
    top = max(scores)
    return 1.0 / sum(math.exp(s - top) for s in scores)


def bootstrap(values: np.ndarray, rng: np.random.Generator, resamples: int) -> list[float]:
    """Mean and 95% percentile interval over cases."""
    idx = rng.integers(0, len(values), size=(resamples, len(values)))
    means = values[idx].mean(axis=1)
    return [float(values.mean()), float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5))]


def select_cases(test: list[dict[str, Any]], index: PoiIndex, raw2item: dict[int, int],
                 n_cases: int, seed: int, exclude: set[int]
                 ) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Draw cases in a seeded order, skipping excluded test indices, until n pass the filters."""
    order = list(range(len(test)))
    random.Random(seed).shuffle(order)
    counts = {"seen": 0, "revisit": 0, "no_metadata": 0, "not_in_model": 0,
              "beyond_reach": 0, "fewer_than_2_candidates": 0, "used": 0}
    chosen = []
    for i in order:
        if len(chosen) >= n_cases:
            break
        if i in exclude:
            continue
        case = test[i]
        counts["seen"] += 1
        history = [int(e["raw_location_id"]) for e in case["history_events"]]
        target = int(case["target_event"]["raw_location_id"])
        if target in history:
            counts["revisit"] += 1
            continue
        last, goal = index.points.get(history[-1]), index.points.get(target)
        if last is None or goal is None or not goal.category:
            counts["no_metadata"] += 1
            continue
        if target not in raw2item or not any(raw in raw2item for raw in history):
            counts["not_in_model"] += 1
            continue
        candidates = index.nearest_in_categories(
            [goal.category], last, k=len(index.points), radius_km=REACH_KM, exclude=set(history)
        )
        if target not in {point.raw_id for _, point in candidates}:
            counts["beyond_reach"] += 1
            continue
        if len(candidates) < 2:
            counts["fewer_than_2_candidates"] += 1
            continue
        counts["used"] += 1
        chosen.append({"index": i, "history": history, "target": target,
                       "category": goal.category, "candidates": candidates})
    return chosen, counts


def request_for(category: str, strength: str) -> Intent:
    return Intent(
        query=f"a {category.strip()}",
        source="user_edit",
        strength=strength,
        want=[CategoryMatch(category_name=category, phrase=category.strip().lower(),
                            method="user_edit")],
        travel_mode="drive",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test-split", required=True, type=Path)
    parser.add_argument("--cases", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--exclude-seeds", type=int, nargs="*", default=[],
                        help="earlier samples (same --cases), in the order they were drawn")
    parser.add_argument("--variants", nargs="*", default=[short(v) for v in VARIANTS],
                        choices=[short(v) for v in VARIANTS])
    parser.add_argument("--strength", choices=["soft", "firm"], default="soft")
    parser.add_argument("--resamples", type=int, default=1000)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    config = RecommendationConfig.from_env()
    index = PoiIndex.from_metadata(config.poi_metadata_path)
    shared = RecommendationService(config)
    shared.poi_index = index
    variants = {name: RecommendationService(dataclasses.replace(config, **changes))
                for name, changes in VARIANTS.items() if short(name) in args.variants}
    for service in variants.values():  # the variants differ only in configuration
        service.sbr_model = shared.sbr_model
        service.poi_index = index
        service.spatial_reranker = shared._spatial()
        service.semantic_reranker = shared._semantic()
        service.intent_scorer = shared._intent_scorer()
    methods = BASELINES + list(variants)

    metadata = json.loads(config.poi_metadata_path.read_text(encoding="utf-8"))
    rows = metadata.values() if isinstance(metadata, dict) else metadata
    checkins = {int(r["raw_poi_id"]): int(r.get("checkins_count") or 0) for r in rows}
    shared.sbr_model._ensure_mappings_loaded()
    raw2item = shared.sbr_model.raw2item

    test = json.loads(args.test_split.read_text(encoding="utf-8"))
    excluded: set[int] = set()
    for earlier in args.exclude_seeds:
        drawn, _ = select_cases(test, index, raw2item, args.cases, earlier, excluded)
        excluded |= {case["index"] for case in drawn}
    cases, counts = select_cases(test, index, raw2item, args.cases, args.seed, excluded)
    print(f"cases used {len(cases)}; excluded from earlier samples {len(excluded)}; "
          f"filters: {counts}", flush=True)

    per_case = []
    started = time.perf_counter()
    for i, case in enumerate(cases, start=1):
        history, target = case["history"], case["target"]
        ids_by_distance = [point.raw_id for _, point in case["candidates"]]
        intent = request_for(case["category"], args.strength)
        controls = controls_for(intent, config)

        habit = shared.sbr_model.score(history, ids_by_distance)
        by_habit = sorted(ids_by_distance, key=lambda r: (-habit.get(r, -math.inf), r))
        # Stable sort: equal check-ins keep the nearer place first.
        by_checkins = sorted(ids_by_distance, key=lambda r: -checkins.get(r, 0))

        ranks: dict[str, int | None] = {
            "M1 nearest": rank_of(target, ids_by_distance),
            "M2 most check-ins": rank_of(target, by_checkins),
            "M3 habit alone": rank_of(target, by_habit),
        }
        for name, service in variants.items():
            ranked, _, _ = service.rank_session(history, step=1, intent=intent,
                                                controls=controls, route_stops=[])
            ranks[name] = rank_of(target, [int(row["raw_poi_id"]) for row in ranked])

        scores = {name: metrics_from_rank(rank) for name, rank in ranks.items()}
        scores["M0 random"] = random_expectation(len(ids_by_distance))
        per_case.append({"index": case["index"], "history_len": len(history),
                         "pool": len(ids_by_distance),
                         "confidence": model_confidence(list(habit.values())),
                         "ranks": ranks, "scores": scores})
        if i % 500 == 0:
            rate = i / (time.perf_counter() - started)
            print(f"{i}/{len(cases)} cases, {rate:.1f}/s", flush=True)

    rng = np.random.default_rng(args.seed)

    def summary(subset: list[dict[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {"cases": len(subset)}
        for method in methods:
            values = np.array([c["scores"][method] for c in subset])
            out[method] = {metric: bootstrap(values[:, j], rng, args.resamples)
                           for j, metric in enumerate(["HR@1", "HR@5", "MRR"])}
        pairs = [(v, b) for v in list(variants) + ["M3 habit alone"]
                 for b in ["M1 nearest", "M2 most check-ins", *variants] if v != b]
        for v, b in pairs:
            diff = np.array([c["scores"][v][2] - c["scores"][b][2] for c in subset])
            out[f"MRR {short(v)} - {short(b)}"] = bootstrap(diff, rng, args.resamples)
        return out

    buckets = {
        "all": per_case,
        "history 1": [c for c in per_case if c["history_len"] == 1],
        "history 2": [c for c in per_case if c["history_len"] == 2],
        "history 3+": [c for c in per_case if c["history_len"] >= 3],
        "pool 2-5": [c for c in per_case if c["pool"] <= 5],
        "pool 6-20": [c for c in per_case if 6 <= c["pool"] <= 20],
        "pool 21+": [c for c in per_case if c["pool"] > 20],
    }
    for name, low, high in CONFIDENCE_BUCKETS:
        buckets[name] = [c for c in per_case
                         if c["confidence"] is not None and low <= c["confidence"] < high]
    kept = {name: sum(c["ranks"][name] is not None for c in per_case) / max(1, len(per_case))
            for name in variants}
    lam = controls_for(request_for("Museum", args.strength), config).habit_intent
    result = {
        "design": ["experiments/E-B_habit_within_request.md",
                   "experiments/E-B2_confidence_aware_habit.md"],
        "settings": {"cases": args.cases, "seed": args.seed, "exclude_seeds": args.exclude_seeds,
                     "variants": list(variants), "strength": args.strength, "lambda": lam,
                     "reach_km": REACH_KM, "intent_k": config.intent_k,
                     "resamples": args.resamples, "device": config.device},
        "filters": counts,
        "target_kept": kept,
        "results": {name: summary(subset) for name, subset in buckets.items() if subset},
        "case_indices": [c["index"] for c in per_case],
    }
    args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")

    print("\ntarget among the places each variant kept: "
          + ", ".join(f"{short(n)} {v:.1%}" for n, v in kept.items()))
    print(f"{'method':34} {'HR@1':>22} {'HR@5':>22} {'MRR':>22}")
    for method in methods:
        cells = [result["results"]["all"][method][m] for m in ("HR@1", "HR@5", "MRR")]
        print(f"{method:34} " + " ".join(f"{v[0]:.3f} [{v[1]:.3f}, {v[2]:.3f}]" for v in cells))
    for key, v in result["results"]["all"].items():
        if key.startswith("MRR "):
            print(f"{key:34} {v[0]:+.3f} [{v[1]:+.3f}, {v[2]:+.3f}]")


if __name__ == "__main__":
    main()
