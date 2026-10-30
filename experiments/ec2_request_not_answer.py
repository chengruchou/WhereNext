"""E-C2: the filter against soft weighting when the request is not the answer.

Design and predictions, written before this ran: experiments/E-C2_request_not_answer.md.
No external API is called.

    python experiments/ec2_request_not_answer.py --test-split <path> --out ec2.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from contracts.intent import CategoryMatch, Intent, SteeringControls
from eb_habit_within_request import rank_of, select_cases
from offline_suite import EXPLORE, REACH_KM, Setup
from services.intent_parser import CategoryVocabulary

SETTINGS = (("F", 0.5), ("W0.5", 0.5), ("W0.8", 0.8))
REQUESTS = ("R1", "R2", "R3")


def session_key(case: dict[str, Any]) -> tuple[int, str]:
    """The test split repeats a session at every history length; its first check-in names it."""
    first = case["history_events"][0]
    return int(first["raw_location_id"]), str(first.get("timestamp"))


def earlier_sessions(setup: Setup) -> set[tuple[int, str]]:
    """Sessions any earlier sample drew from: E-B (7-9), E-C (10), E-F (11), E-D1 (12, 13)."""
    indices: set[int] = set()
    used: set[int] = set()
    for seed in (7, 8, 9):
        cases, _ = select_cases(setup.test, setup.index, setup.raw2item, 2000, seed, set(used))
        used |= {c["index"] for c in cases}
    indices |= used
    cases, _ = select_cases(setup.test, setup.index, setup.raw2item, 1000, 10, set())
    indices |= {c["index"] for c in cases}
    for n, seed in ((2000, 10), (2000, 11), (150, 12), (300, 13)):
        cases, _ = setup.new_place_cases(n, seed)
        indices |= {c["index"] for c in cases}
    return {session_key(setup.test[i]) for i in indices}


def draw(setup: Setup, n: int, seed: int, excluded: set[tuple[int, str]]):
    order = list(range(len(setup.test)))
    random.Random(seed).shuffle(order)
    counts = {"seen": 0, "earlier_session": 0, "session_taken": 0, "revisit": 0, "other": 0}
    taken: set[tuple[int, str]] = set()
    chosen = []
    for i in order:
        if len(chosen) >= n:
            break
        case = setup.test[i]
        counts["seen"] += 1
        key = session_key(case)
        if key in excluded:
            counts["earlier_session"] += 1
            continue
        if key in taken:
            counts["session_taken"] += 1
            continue
        history = [int(e["raw_location_id"]) for e in case["history_events"]]
        target = int(case["target_event"]["raw_location_id"])
        if target in history:
            counts["revisit"] += 1
            continue
        last, goal = setup.index.points.get(history[-1]), setup.index.points.get(target)
        if (last is None or goal is None or not goal.category or target not in setup.raw2item
                or not any(raw in setup.raw2item for raw in history)):
            counts["other"] += 1
            continue
        taken.add(key)
        chosen.append({"index": i, "history": history, "target": target,
                       "category": goal.category})
    counts["used"] = len(chosen)
    return chosen, counts


def request(categories: list[str], query: str) -> Intent:
    want = [CategoryMatch(category_name=c, phrase=query, method="user_edit") for c in categories]
    return Intent(query=query, source="user_edit", strength="soft", want=want, travel_mode="drive")


def boot(values: np.ndarray, idx: np.ndarray, stat=np.mean) -> list[float]:
    stats = np.array([stat(values[row]) for row in idx])
    return [float(stat(values)), float(np.percentile(stats, 2.5)),
            float(np.percentile(stats, 97.5))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test-split", required=True, type=Path)
    parser.add_argument("--cases", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=14)
    parser.add_argument("--resamples", type=int, default=1000)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()

    setup = Setup(args.test_split)
    vocabulary = CategoryVocabulary.from_metadata(setup.config.poi_metadata_path)
    services = {"F": setup.base, "W": setup.variant(intent_filter=False)}
    position = {int(raw): i for i, raw in enumerate(setup.ids)}

    cases, counts = draw(setup, args.cases, args.seed, earlier_sessions(setup))
    print(f"{len(cases)} cases; filters: {counts}", flush=True)

    pick = random.Random(args.seed)
    rows = []
    for n, case in enumerate(cases, start=1):
        history, target, category = case["history"], case["target"], case["category"]
        km = setup.km_from(history[-1])
        group = vocabulary.lexical(category.strip())
        if category not in group:
            group = [category] + group[:7]
        types = {g.strip() for g in group}  # the metadata spells some types with a trailing space
        visited = set(history)
        nearby = setup.cats[(km <= REACH_KM["drive"]) & ~np.isin(setup.ids, list(visited))]
        others = sorted({c for c in nearby if c and c.strip() not in types})
        other = pick.choice(others) if others else None
        requests = {"R1": request([category], category.strip().lower()),
                    "R2": request(group, category.strip().lower())}
        if other is not None:
            requests["R3"] = request([other], other.strip().lower())

        row: dict[str, Any] = {
            "index": case["index"], "group_size": len(types), "other": other,
            "target_km": float(km[position[target]]) if target in position else None,
        }
        habit, _, _ = setup.base.rank_session(history, route_stops=[])
        row["N km"] = float(km[position[int(habit[0]["raw_poi_id"])]]) if habit else None

        for rid, intent in requests.items():
            wanted = {m.category_name for m in intent.want}
            for name, lam in SETTINGS:
                controls = SteeringControls(habit_intent=lam, explore=EXPLORE, source="inspector")
                ranked, _, _ = services[name[0]].rank_session(
                    history, intent=intent, controls=controls, route_stops=[])
                ids = [int(r["raw_poi_id"]) for r in ranked]
                rank = rank_of(target, ids)
                key = f"{rid} {name}"
                row[f"{key} rr"] = 0.0 if rank is None else 1.0 / rank
                row[f"{key} hr1"] = float(rank == 1)
                row[f"{key} hr5"] = float(rank is not None and rank <= 5)
                first = setup.index.points.get(ids[0]) if ids else None
                row[f"{key} met"] = float(first is not None and first.category in wanted)
                row[f"{key} km"] = float(km[position[ids[0]]]) if ids else None
        rows.append(row)
        if n % 100 == 0:
            print(f"{n}/{len(cases)} cases, {time.perf_counter() - started:.0f} s", flush=True)

    rng = np.random.default_rng(args.seed)
    results: dict[str, Any] = {"cases": len(rows), "filters": counts}

    def subset_stats(rid: str, subset: list[dict[str, Any]], label: str) -> None:
        idx = rng.integers(0, len(subset), size=(args.resamples, len(subset)))
        out: dict[str, Any] = {"cases": len(subset)}
        for name, _ in SETTINGS:
            key = f"{rid} {name}"
            out[name] = {m: boot(np.array([r[f"{key} {m}"] for r in subset]), idx)
                         for m in ("rr", "hr1", "hr5", "met")}
            legs = np.array([r[f"{key} km"] for r in subset if r[f"{key} km"] is not None])
            legs_idx = rng.integers(0, len(legs), size=(args.resamples, len(legs)))
            out[name]["km median"] = boot(legs, legs_idx, np.median)
            out[name]["km > 10"] = boot((legs > 10).astype(float), legs_idx)
        for a, b in (("F", "W0.5"), ("F", "W0.8")):
            for m in ("rr", "hr5"):
                diff = np.array([r[f"{rid} {a} {m}"] - r[f"{rid} {b} {m}"] for r in subset])
                out[f"{a} - {b} {m}"] = boot(diff, idx)
        habit = np.array([r["N km"] for r in subset if r["N km"] is not None])
        habit_idx = rng.integers(0, len(habit), size=(args.resamples, len(habit)))
        out["N km median"] = boot(habit, habit_idx, np.median)
        out["N km > 10"] = boot((habit > 10).astype(float), habit_idx)
        results[label] = out

    within = [r for r in rows if r["target_km"] is not None and r["target_km"] <= REACH_KM["drive"]]
    subset_stats("R1", rows, "R1 all cases")
    subset_stats("R1", within, "R1 next place within 40 km")
    grouped = [r for r in rows if r["group_size"] >= 2]
    subset_stats("R2", grouped, "R2 group of two or more types")
    mismatched = [r for r in rows if r["other"] is not None]
    subset_stats("R3", mismatched, "R3 another type")

    # Mixing a share p of R3 requests into R1: crossover where F meets each soft weighting.
    idx = rng.integers(0, len(mismatched), size=(args.resamples, len(mismatched)))

    def crossover(sel: np.ndarray, other: str) -> float:
        gap = {rid: np.mean([mismatched[i][f"{rid} F rr"] - mismatched[i][f"{rid} {other} rr"]
                             for i in sel]) for rid in ("R1", "R3")}
        return float(gap["R1"] / (gap["R1"] - gap["R3"])) if gap["R1"] != gap["R3"] else np.nan

    for other in ("W0.5", "W0.8"):
        point = crossover(np.arange(len(mismatched)), other)
        draws = np.array([crossover(row, other) for row in idx])
        results[f"crossover F vs {other}"] = [point, float(np.nanpercentile(draws, 2.5)),
                                              float(np.nanpercentile(draws, 97.5))]

    results["minutes"] = (time.perf_counter() - started) / 60
    args.out.write_text(json.dumps({"results": results, "rows": rows}, indent=1), encoding="utf-8")

    for label, out in results.items():
        if not isinstance(out, dict) or "F" not in out:
            continue
        print(f"\n{label} ({out['cases']} cases)")
        print(f"{'':6}{'MRR':>22}{'HR@1':>8}{'HR@5':>8}{'met':>8}{'km p50':>9}{'>10 km':>8}")
        for name, _ in SETTINGS:
            s = out[name]
            print(f"{name:6}{s['rr'][0]:8.3f} [{s['rr'][1]:.3f}, {s['rr'][2]:.3f}]"
                  f"{s['hr1'][0]:8.3f}{s['hr5'][0]:8.3f}{s['met'][0]:8.3f}"
                  f"{s['km median'][0]:9.2f}{s['km > 10'][0]:8.3f}")
        print(f"{'N':6}{'':38}{out['N km median'][0]:17.2f}{out['N km > 10'][0]:8.3f}")
        for k in ("F - W0.5 rr", "F - W0.8 rr", "F - W0.5 hr5", "F - W0.8 hr5"):
            v = out[k]
            print(f"  {k}: {v[0]:+.3f} [{v[1]:+.3f}, {v[2]:+.3f}]")
    for other in ("W0.5", "W0.8"):
        v = results[f"crossover F vs {other}"]
        print(f"crossover p* F vs {other}: {v[0]:.3f} [{v[1]:.3f}, {v[2]:.3f}]")
    print(f"{results['minutes']:.1f} minutes")


if __name__ == "__main__":
    main()
