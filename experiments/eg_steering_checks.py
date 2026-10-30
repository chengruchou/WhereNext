"""E-G: wording-derived weights, unmet requests on foot, and evidence that adds up.

Design and predictions, written before this ran: experiments/E-G_steering_checks.md.
No external API is called.

    python experiments/eg_steering_checks.py --test-split <path> --out eg.json
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from ec2_request_not_answer import draw, earlier_sessions, request, session_key
from ed1_verifier_mutation import OfflineRoutes
from offline_suite import REACH_KM, Setup
from services.intent_parser import CategoryVocabulary

WORDING = {"default": ("soft", "balanced"), "firm": ("firm", "balanced"),
           "new": ("soft", "new"), "familiar": ("soft", "familiar")}


class MismatchCounter(logging.Handler):
    """Counts the evidence builder's warning that a record does not add up to its score."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if "differs from pipeline score" in record.getMessage():
            self.count += 1


def worded(intent, strength: str, explore: str):
    return intent.model_copy(update={"strength": strength, "explore": explore})


def share(values: list[float]) -> float:
    return float(np.mean(values)) if values else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test-split", required=True, type=Path)
    parser.add_argument("--cases", type=int, default=500)
    parser.add_argument("--seed", type=int, default=15)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()

    setup = Setup(args.test_split)
    routes = OfflineRoutes(setup)
    vocabulary = CategoryVocabulary.from_metadata(setup.config.poi_metadata_path)
    counter = MismatchCounter()
    logging.getLogger("services.evidence_builder").addHandler(counter)

    excluded = earlier_sessions(setup)
    c2, _ = draw(setup, 1000, 14, excluded)  # E-C2's sample
    excluded |= {session_key(setup.test[c["index"]]) for c in c2}
    cases, counts = draw(setup, args.cases, args.seed, excluded)
    print(f"{len(cases)} cases; filters: {counts}", flush=True)

    pick = random.Random(args.seed)
    rows, records = [], 0
    for n, case in enumerate(cases, start=1):
        history, category = case["history"], case["category"]
        history_types = {(setup.index.points[r].category or "").strip() for r in history
                         if r in setup.index.points}
        km = setup.km_from(history[-1])
        group = vocabulary.lexical(category.strip())
        if category not in group:
            group = [category] + group[:7]
        types = {g.strip() for g in group}
        nearby = setup.cats[(km <= REACH_KM["drive"]) & ~np.isin(setup.ids, history)]
        others = sorted({c for c in nearby if c and c.strip() not in types})
        requests = {"R1": request([category], category.strip().lower())}
        if len(types) >= 2:
            requests["R2"] = request(group, category.strip().lower())
        if others:
            other = pick.choice(others)
            requests["R3"] = request([other], other.strip().lower())

        row: dict[str, Any] = {"index": case["index"]}
        for rid, intent in requests.items():
            for name, (strength, explore) in WORDING.items():
                ev = routes.evidence(history, worded(intent, strength, explore))
                records += len(ev["steps"])
                stops = [s["poi"]["raw_poi_id"] for s in ev["steps"]]
                row[f"{rid} {name} stops"] = stops
                row[f"{rid} {name} in history types"] = [
                    (s["poi"]["category_name"] or "").strip() in history_types for s in ev["steps"]]

        walk = request([category], category.strip().lower()).model_copy(
            update={"travel_mode": "walk"})
        ev = routes.evidence(history, walk)
        records += len(ev["steps"])
        if ev["steps"]:
            first = ev["steps"][0]
            row["walk in range"] = (first.get("intent") or {}).get("in_range")
            row["walk first km"] = (first.get("travel") or {}).get("distance_km")
        rows.append(row)
        if n % 50 == 0:
            print(f"{n}/{len(cases)} cases, {time.perf_counter() - started:.0f} s", flush=True)

    results: dict[str, Any] = {"cases": len(rows), "filters": counts}
    for rid in ("R1", "R2", "R3"):
        have = [r for r in rows if f"{rid} default stops" in r]
        out: dict[str, Any] = {"cases": len(have)}
        for name in ("firm", "new", "familiar"):
            pairs = [(r[f"{rid} default stops"], r[f"{rid} {name} stops"]) for r in have]
            out[f"{name}: first stop differs"] = share(
                [float(a[:1] != b[:1]) for a, b in pairs])
            out[f"{name}: route differs"] = share([float(a != b) for a, b in pairs])
        for name in WORDING:
            flags = [f for r in have for f in r[f"{rid} {name} in history types"]]
            out[f"{name}: stops in a history type"] = share([float(f) for f in flags])
        results[f"G1 {rid}"] = out

    walked = [r for r in rows if r.get("walk first km") is not None]
    met = [r["walk first km"] for r in walked if (r["walk in range"] or 0) > 0]
    unmet = np.array([r["walk first km"] for r in walked if r["walk in range"] == 0])
    results["G2"] = {
        "met": len(met), "met: first leg <= 2 km": share([float(k <= 2.0 + 1e-9) for k in met]),
        "unmet": len(unmet),
        "unmet: median first leg km": float(np.median(unmet)) if len(unmet) else None,
        "unmet: first leg > 2 km": share((unmet > 2.0).astype(float).tolist()),
        "unmet: first leg > 10 km": share((unmet > 10.0).astype(float).tolist()),
    }
    results["G3"] = {"records": records, "not adding up": counter.count}
    results["minutes"] = (time.perf_counter() - started) / 60
    args.out.write_text(json.dumps({"results": results, "rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
