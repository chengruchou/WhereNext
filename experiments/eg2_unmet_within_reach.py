"""E-G2: an unmet request's stops with and without the reach limit.

Design and predictions, written before this ran: experiments/E-G2_unmet_within_reach.md.
Uses E-G's 500 cases; no external API is called.

    python experiments/eg2_unmet_within_reach.py --test-split <path> --out eg2.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from contracts.intent import SteeringControls
from eb_habit_within_request import rank_of
from ec2_request_not_answer import draw, earlier_sessions, request, session_key
from ed1_verifier_mutation import OfflineRoutes
from offline_suite import EXPLORE, REACH_KM, Setup

MODES = ("walk", "drive")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test-split", required=True, type=Path)
    parser.add_argument("--cases", type=int, default=500)
    parser.add_argument("--seed", type=int, default=15)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()

    setup = Setup(args.test_split)
    excluded = earlier_sessions(setup)
    c2, _ = draw(setup, 1000, 14, excluded)  # E-C2's sample, as in E-G
    excluded |= {session_key(setup.test[c["index"]]) for c in c2}
    cases, _ = draw(setup, args.cases, args.seed, excluded)

    variants = {"off": setup.variant(intent_unmet_within_reach=False),
                "on": setup.variant(intent_unmet_within_reach=True)}
    routes = OfflineRoutes(setup)
    rows = []
    for n, case in enumerate(cases, start=1):
        history, target, category = case["history"], case["target"], case["category"]
        row: dict[str, Any] = {"index": case["index"]}
        for mode in MODES:
            intent = request([category], category.strip().lower()).model_copy(
                update={"travel_mode": mode})
            for name, service in variants.items():
                routes.service = service
                ev = routes.evidence(history, intent)
                key = f"{mode} {name}"
                row[f"{key} stops"] = [s["poi"]["raw_poi_id"] for s in ev["steps"]]
                row[f"{key} hops"] = [(s.get("travel") or {}).get("distance_km")
                                      for s in ev["steps"]]
                row[f"{key} unmet"] = [(s.get("intent") or {}).get("in_range") == 0
                                       for s in ev["steps"]]
                controls = SteeringControls(habit_intent=0.5, explore=EXPLORE, source="intent")
                ranked, _, _ = service.rank_session(history, intent=intent, controls=controls,
                                                    route_stops=[])
                rank = rank_of(target, [int(r["raw_poi_id"]) for r in ranked])
                row[f"{key} rr"] = 0.0 if rank is None else 1.0 / rank
        rows.append(row)
        if n % 50 == 0:
            print(f"{n}/{len(cases)} cases, {time.perf_counter() - started:.0f} s", flush=True)

    results: dict[str, Any] = {"cases": len(rows)}
    for mode in MODES:
        reach = REACH_KM[mode]
        out: dict[str, Any] = {}
        first_unmet = [r for r in rows if r[f"{mode} off unmet"][:1] == [True]]
        out["cases unmet at the first step"] = len(first_unmet)
        for name in ("off", "on"):
            key = f"{mode} {name}"
            first = np.array([r[f"{key} hops"][0] for r in first_unmet])
            unmet_hops = np.array([h for r in rows for h, u in
                                   zip(r[f"{key} hops"], r[f"{key} unmet"], strict=True) if u])
            all_hops = np.array([h for r in rows for h in r[f"{key} hops"]])
            out[name] = {
                "first leg, unmet: median km": float(np.median(first)),
                f"first leg, unmet: over {reach:g} km": float(np.mean(first > reach)),
                "first leg, unmet: over 10 km": float(np.mean(first > 10)),
                "unmet steps": len(unmet_hops),
                f"unmet steps: over {reach:g} km": float(np.mean(unmet_hops > reach)),
                f"all hops: over {reach:g} km": float(np.mean(all_hops > reach)),
                "unmet at first step: MRR of the next place": float(
                    np.mean([r[f"{key} rr"] for r in first_unmet])),
            }
        always_met = [r for r in rows if not any(r[f"{mode} off unmet"])]
        out["routes met at every step"] = len(always_met)
        out["routes met at every step: identical"] = float(np.mean(
            [r[f"{mode} off stops"] == r[f"{mode} on stops"] for r in always_met]))
        results[mode] = out
    results["minutes"] = (time.perf_counter() - started) / 60
    args.out.write_text(json.dumps({"results": results, "rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
