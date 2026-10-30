"""E-N: the novelty weight when the request names no type.

Design and predictions, written before this ran: experiments/E-N_novelty_without_request.md.
No external API is called.

    python experiments/en_novelty_without_request.py --test-split <path> --out en.json
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

from contracts.intent import Intent
from eb_habit_within_request import rank_of
from ec2_request_not_answer import draw, earlier_sessions, session_key
from ed1_verifier_mutation import OfflineRoutes
from offline_suite import Setup
from services.intent_parser import controls_for

SETTINGS = ("familiar", "balanced", "new")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test-split", required=True, type=Path)
    parser.add_argument("--cases", type=int, default=500)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()

    setup = Setup(args.test_split)
    excluded = earlier_sessions(setup)
    for n, seed in ((1000, 14), (500, 15)):  # E-C2 and E-G
        drawn, _ = draw(setup, n, seed, excluded)
        excluded |= {session_key(setup.test[c["index"]]) for c in drawn}
    cases, counts = draw(setup, args.cases, args.seed, excluded)
    print(f"{len(cases)} cases; filters: {counts}", flush=True)

    routes = OfflineRoutes(setup)
    rows = []
    for n, case in enumerate(cases, start=1):
        history, target = case["history"], case["target"]
        history_types = {(setup.index.points[r].category or "").strip() for r in history
                         if r in setup.index.points}
        row: dict[str, Any] = {"index": case["index"]}
        for name in SETTINGS:
            intent = Intent(query=f"somewhere ({name})", source="user_edit", explore=name)
            ev = routes.evidence(history, intent)
            row[f"{name} stops"] = [s["poi"]["raw_poi_id"] for s in ev["steps"]]
            row[f"{name} familiar"] = [(s["poi"]["category_name"] or "").strip() in history_types
                                       for s in ev["steps"]]
            row[f"{name} first km"] = ((ev["steps"][0].get("travel") or {}).get("distance_km")
                                       if ev["steps"] else None)
            ranked, _, _ = setup.base.rank_session(
                history, intent=intent, controls=controls_for(intent, setup.config),
                route_stops=[])
            rank = rank_of(target, [int(r["raw_poi_id"]) for r in ranked])
            row[f"{name} rank"] = rank
        rows.append(row)
        if n % 50 == 0:
            print(f"{n}/{len(cases)} cases, {time.perf_counter() - started:.0f} s", flush=True)

    results: dict[str, Any] = {"cases": len(rows), "filters": counts}
    for name in SETTINGS:
        ranks = [r[f"{name} rank"] for r in rows]
        legs = [r[f"{name} first km"] for r in rows if r[f"{name} first km"] is not None]
        out = {
            "stops in a history type": float(np.mean(
                [f for r in rows for f in r[f"{name} familiar"]])),
            "HR@1": float(np.mean([k == 1 for k in ranks])),
            "HR@10": float(np.mean([k is not None and k <= 10 for k in ranks])),
            "MRR": float(np.mean([0.0 if k is None else 1.0 / k for k in ranks])),
            "median first leg km": float(np.median(legs)),
        }
        if name != "balanced":
            out["first stop differs from balanced"] = float(np.mean(
                [r[f"{name} stops"][:1] != r["balanced stops"][:1] for r in rows]))
            out["route differs from balanced"] = float(np.mean(
                [r[f"{name} stops"] != r["balanced stops"] for r in rows]))
        results[name] = out
    results["minutes"] = (time.perf_counter() - started) / 60
    args.out.write_text(json.dumps({"results": results, "rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
