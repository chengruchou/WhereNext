"""E-C, E-E and E-F: the offline experiments (no external API is called).

Designs and predictions, each written before its run: experiments/E-C_filter_vs_weighting.md,
experiments/E-E_latency.md and experiments/E-F_no_request_accuracy.md.

Run from the repository root, with the model files set through the WHERENEXT_* variables:

    python experiments/offline_suite.py --experiment C --test-split <path> --out ec.json
    python experiments/offline_suite.py --experiment F --test-split <path> --out ef.json
    python experiments/offline_suite.py --experiment E --test-split <path> --out ee.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import random
import sys
import time
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from contracts.intent import SteeringControls
from eb_habit_within_request import bootstrap, rank_of, request_for, select_cases
from services.model_config import RecommendationConfig
from services.recommendation_service import RecommendationService
from services.steering import PoiIndex

EARTH_RADIUS_KM = 6371.0088
REACH_KM = {"walk": 2.0, "transit": 15.0, "drive": 40.0}
WEIGHTINGS = (0.2, 0.5, 0.8, 1.0)
EXPLORE = 0.1  # the "balanced" default, the same in every setting


class Setup:
    """The loaded model, index and metadata, shared by every service variant."""

    def __init__(self, test_split: Path):
        self.config = RecommendationConfig.from_env()
        self.index = PoiIndex.from_metadata(self.config.poi_metadata_path)
        self.base = RecommendationService(self.config)
        self.base.poi_index = self.index
        self.base.sbr_model._ensure_mappings_loaded()
        self.raw2item = self.base.sbr_model.raw2item
        self.test = json.loads(test_split.read_text(encoding="utf-8"))
        points = list(self.index.points.values())
        self.ids = np.array([p.raw_id for p in points])
        self.lat = np.radians([p.lat for p in points])
        self.lng = np.radians([p.lng for p in points])
        self.cats = np.array([p.category or "" for p in points], dtype=object)

    def variant(self, **changes: Any) -> RecommendationService:
        service = RecommendationService(dataclasses.replace(self.config, **changes))
        service.sbr_model = self.base.sbr_model
        service.poi_index = self.index
        service.spatial_reranker = self.base._spatial()
        service.semantic_reranker = self.base._semantic()
        service.intent_scorer = self.base._intent_scorer()
        return service

    def km_from(self, raw_id: int) -> np.ndarray:
        p = self.index.points[raw_id]
        lat0, lng0 = math.radians(p.lat), math.radians(p.lng)
        h = (np.sin((self.lat - lat0) / 2) ** 2
             + np.cos(lat0) * np.cos(self.lat) * np.sin((self.lng - lng0) / 2) ** 2)
        return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(h))

    def new_place_cases(self, n: int, seed: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Cases whose next place is new to the user and known to the model and metadata."""
        order = list(range(len(self.test)))
        random.Random(seed).shuffle(order)
        counts = {"seen": 0, "revisit": 0, "excluded_other": 0, "used": 0}
        chosen = []
        for i in order:
            if len(chosen) >= n:
                break
            case = self.test[i]
            counts["seen"] += 1
            history = [int(e["raw_location_id"]) for e in case["history_events"]]
            target = int(case["target_event"]["raw_location_id"])
            if target in history:
                counts["revisit"] += 1
                continue
            last, goal = self.index.points.get(history[-1]), self.index.points.get(target)
            if (last is None or goal is None or not goal.category or target not in self.raw2item
                    or not any(raw in self.raw2item for raw in history)):
                counts["excluded_other"] += 1
                continue
            counts["used"] += 1
            chosen.append({"index": i, "history": history, "target": target,
                           "category": goal.category})
        return chosen, counts


def build_route(service: RecommendationService, history: list[int], stops: int = 3,
                intent=None, controls=None, plan: bool = True):
    """Greedy route as /route builds it; plan=False leaves out the route costs."""
    chosen: list[int] = []
    stages = []
    for step in range(1, stops + 1):
        rows, step_stages, _ = service.rank_session(
            history + chosen, step=step, intent=intent, controls=controls,
            route_stops=list(chosen) if plan else None,
        )
        stages.extend(step_stages)
        if not rows:
            break
        chosen.append(int(rows[0]["raw_poi_id"]))
    return chosen, stages


def percentiles(values: list[float]) -> dict[str, float]:
    return {"p50": float(np.percentile(values, 50)), "p95": float(np.percentile(values, 95)),
            "n": len(values)}


# ---- E-C ---------------------------------------------------------------------------------

def run_c(setup: Setup, args, rng: np.random.Generator) -> dict[str, Any]:
    # C1: can a request for the next place's type be met within each mode's reach?
    feas_cases, feas_counts = setup.new_place_cases(args.feasibility_cases, args.seed)
    met = {mode: [] for mode in REACH_KM}
    for case in feas_cases:
        last = setup.index.points[case["history"][-1]]
        for mode, radius in REACH_KM.items():
            found = setup.index.nearest_in_categories(
                [case["category"]], last, k=1, radius_km=radius, exclude=set(case["history"]))
            met[mode].append(1.0 if found else 0.0)
    c1 = {mode: bootstrap(np.array(v), rng, args.resamples) for mode, v in met.items()}
    print(f"C1 feasibility ({len(feas_cases)} cases): "
          + ", ".join(f"{m} {v[0]:.1%}" for m, v in c1.items()), flush=True)

    # C2 and C3 on E-B-style cases.
    cases, counts = select_cases(setup.test, setup.index, setup.raw2item, args.cases,
                                 args.seed, set())
    filtered = setup.base
    weighted = setup.variant(intent_filter=False)
    settings = [("F", filtered, 0.5)] + [(f"W{lam:g}", weighted, lam) for lam in WEIGHTINGS]
    pick = random.Random(args.seed)
    per_case = []
    for i, case in enumerate(cases, start=1):
        history, target = case["history"], case["target"]
        last = case["history"][-1]
        dist = setup.km_from(last)
        visited_cats = {setup.index.points[r].category for r in history if r in setup.index.points}
        nearby = setup.cats[(dist <= REACH_KM["drive"]) & ~np.isin(setup.ids, history)]
        options = sorted({c for c in nearby if c and c not in visited_cats
                          and c != case["category"]})
        contrary = pick.choice(options) if options else None
        row: dict[str, Any] = {"index": case["index"], "contrary": contrary}
        for name, service, lam in settings:
            controls = SteeringControls(habit_intent=lam, explore=EXPLORE, source="inspector")
            matched, _, _ = service.rank_session(
                history, intent=request_for(case["category"], "soft"), controls=controls,
                route_stops=[])
            rank = rank_of(target, [int(r["raw_poi_id"]) for r in matched])
            row[f"{name} rr"] = 0.0 if rank is None else 1.0 / rank
            row[f"{name} hr5"] = float(rank is not None and rank <= 5)
            if contrary is not None:
                ranked, _, _ = service.rank_session(
                    history, intent=request_for(contrary, "soft"), controls=controls,
                    route_stops=[])
                cats = [r.get("category_name") or setup.index.points[int(r["raw_poi_id"])].category
                        for r in ranked]
                row[f"{name} met@1"] = float(bool(cats) and cats[0] == contrary)
                row[f"{name} share@5"] = (sum(c == contrary for c in cats[:5]) / min(5, len(cats))
                                          if cats else 0.0)
        per_case.append(row)
        if i % 250 == 0:
            print(f"C2/C3 {i}/{len(cases)}", flush=True)

    def agg(key: str, subset: list[dict[str, Any]]) -> list[float]:
        return bootstrap(np.array([r[key] for r in subset]), rng, args.resamples)

    contrary_cases = [r for r in per_case if r["contrary"] is not None]
    c2 = {name: {"met@1": agg(f"{name} met@1", contrary_cases),
                 "share@5": agg(f"{name} share@5", contrary_cases)} for name, _, _ in settings}
    c3 = {name: {"MRR": agg(f"{name} rr", per_case), "HR@5": agg(f"{name} hr5", per_case)}
          for name, _, _ in settings}
    diff = np.array([r["F rr"] - r["W0.5 rr"] for r in per_case])
    c3["MRR F - W0.5"] = bootstrap(diff, rng, args.resamples)
    return {"C1": {"cases": len(feas_cases), "filters": feas_counts, "met": c1},
            "C2": {"cases": len(contrary_cases), **c2},
            "C3": {"cases": len(per_case), "filters": counts, **c3}}


# ---- E-F ---------------------------------------------------------------------------------

def run_f(setup: Setup, args, rng: np.random.Generator) -> dict[str, Any]:
    cases, counts = setup.new_place_cases(args.cases, args.seed)
    pipeline = setup.base
    no_costs = setup.variant(route_repeat_penalty=0.0, route_travel_weight=0.0)
    per_case = []
    for i, case in enumerate(cases, start=1):
        history, target = case["history"], case["target"]
        backbone = [int(r["raw_poi_id"]) for r in
                    setup.base.sbr_model.predict(history, top_k=setup.config.model_top_k)]
        plain, _, _ = no_costs.rank_session(history, route_stops=None)
        costed, _, _ = pipeline.rank_session(history, route_stops=[])
        ranks = {"B": rank_of(target, backbone),
                 "P": rank_of(target, [int(r["raw_poi_id"]) for r in plain]),
                 "R": rank_of(target, [int(r["raw_poi_id"]) for r in costed])}
        row: dict[str, Any] = {"index": case["index"]}
        for name, rank in ranks.items():
            row[f"{name} hr1"] = float(rank == 1)
            row[f"{name} hr5"] = float(rank is not None and rank <= 5)
            row[f"{name} hr10"] = float(rank is not None and rank <= 10)
            row[f"{name} ndcg10"] = (1.0 / math.log2(rank + 1)
                                     if rank is not None and rank <= 10 else 0.0)
        last_cat = setup.index.points[history[-1]].category
        for name, service, plan in (("P", no_costs, False), ("R", pipeline, True)):
            stops, _ = build_route(service, history, plan=plan)
            cats = [setup.index.points[s].category for s in stops]
            path = [history[-1], *stops]
            hops = [_km(setup, a, b) for a, b in pairwise(path)]
            row[f"{name} repeat"] = float(len(set(cats)) < len(cats))
            row[f"{name} same_as_last"] = (sum(c == last_cat for c in cats) / len(cats)
                                          if cats else 0.0)
            row[f"{name} hop_km"] = float(np.mean(hops)) if hops else 0.0
            row[f"{name} hops"] = hops
        per_case.append(row)
        if i % 250 == 0:
            print(f"F {i}/{len(cases)}", flush=True)

    def agg(key: str) -> list[float]:
        return bootstrap(np.array([r[key] for r in per_case]), rng, args.resamples)

    accuracy = {name: {m: agg(f"{name} {m}") for m in ("hr1", "hr5", "hr10", "ndcg10")}
                for name in ("B", "P", "R")}
    for a, b in (("P", "B"), ("R", "P")):
        diff = np.array([r[f"{a} hr10"] - r[f"{b} hr10"] for r in per_case])
        accuracy[f"HR@10 {a} - {b}"] = bootstrap(diff, rng, args.resamples)
    routes = {name: {m: agg(f"{name} {m}") for m in ("repeat", "same_as_last", "hop_km")}
              for name in ("P", "R")}
    if args.rows_out:
        args.rows_out.write_text(json.dumps(per_case), encoding="utf-8")
    return {"cases": len(per_case), "filters": counts, "accuracy": accuracy, "routes": routes}


def _km(setup: Setup, a: int, b: int) -> float:
    pa, pb = setup.index.points[a], setup.index.points[b]
    lat1, lat2 = math.radians(pa.lat), math.radians(pb.lat)
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(pb.lng - pa.lng) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


# ---- E-E ---------------------------------------------------------------------------------

def run_e(args) -> dict[str, Any]:
    cold_start = time.perf_counter()
    setup = Setup(args.test_split)
    cases, _ = setup.new_place_cases(args.cases, args.seed)
    first = cases[0]
    build_route(setup.base, first["history"], stops=1)
    cold_plain = time.perf_counter() - cold_start
    start = time.perf_counter()
    build_route(setup.base, first["history"], stops=1,
                intent=request_for(first["category"], "soft"),
                controls=SteeringControls(habit_intent=0.5, explore=EXPLORE, source="intent"))
    cold_request = time.perf_counter() - start
    for case in cases[1:6]:  # warm-up, untimed
        build_route(setup.base, case["history"])

    stage_ms: dict[str, list[float]] = {}
    route_ms = {"no request": [], "request": []}
    for case in cases[: args.timed]:
        for label, intent in (("no request", None),
                              ("request", request_for(case["category"], "soft"))):
            controls = (SteeringControls(habit_intent=0.5, explore=EXPLORE, source="intent")
                        if intent else None)
            t0 = time.perf_counter()
            _, stages = build_route(setup.base, case["history"], intent=intent,
                                    controls=controls)
            route_ms[label].append((time.perf_counter() - t0) * 1000)
            for s in stages:
                if s.latency_ms is not None:
                    stage_ms.setdefault(f"{label}: {s.stage}", []).append(s.latency_ms)
    return {"cold_start_s": {"load and first route": cold_plain,
                             "first request (loads the intent encoder)": cold_request},
            "stage_ms": {k: percentiles(v) for k, v in stage_ms.items()},
            "route_ms": {k: percentiles(v) for k, v in route_ms.items()},
            "device": setup.config.device, "timed_routes": args.timed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiment", choices=["C", "E", "F"], required=True)
    parser.add_argument("--test-split", required=True, type=Path)
    parser.add_argument("--cases", type=int, default=None)
    parser.add_argument("--feasibility-cases", type=int, default=2000)
    parser.add_argument("--timed", type=int, default=300)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--resamples", type=int, default=1000)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rows-out", type=Path, default=None,
                        help="F only: also write each case's ranks and route hops (for E-R)")
    args = parser.parse_args()
    defaults ={"C": (1000, 10), "F": (2000, 11), "E": (400, 11)}[args.experiment]
    args.cases = args.cases or defaults[0]
    args.seed = args.seed if args.seed is not None else defaults[1]
    rng = np.random.default_rng(args.seed)

    started = time.perf_counter()
    if args.experiment == "E":
        result = run_e(args)
    else:
        setup = Setup(args.test_split)
        result = (run_c if args.experiment == "C" else run_f)(setup, args, rng)
    result["settings"] = {"experiment": args.experiment, "cases": args.cases, "seed": args.seed,
                          "resamples": args.resamples}
    result["minutes"] = (time.perf_counter() - started) / 60
    args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "settings"}, indent=1))


if __name__ == "__main__":
    main()
