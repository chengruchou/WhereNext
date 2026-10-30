"""E-R: E-B and E-F intervals resampled over sessions instead of cases.

Design and predictions, written before this ran: experiments/E-R_session_intervals.md.
Reads the per-case rows that `eb_habit_within_request.py --rows-out` and
`offline_suite.py --experiment F --rows-out` write.

    python experiments/er_session_intervals.py --test-split <path> --eb-rows eb9_rows.json \
        --eb-summary eb9.json --f-rows f_rows.json --f-summary f.json --out er.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

RESAMPLES = 1000
METRICS = ("HR@1", "HR@5", "MRR")


def session_key(case: dict[str, Any]) -> str:
    first = case["history_events"][0]
    return f"{first['raw_location_id']}@{first.get('timestamp')}"


def intervals(values: np.ndarray, sessions: list[str], rng: np.random.Generator):
    """Mean with a case-resampled and a session-resampled 95% interval."""
    n = len(values)
    case_means = values[rng.integers(0, n, size=(RESAMPLES, n))].mean(axis=1)
    groups: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(sessions):
        groups[s].append(i)
    sums = np.array([values[idx].sum() for idx in groups.values()])
    counts = np.array([len(idx) for idx in groups.values()])
    picks = rng.integers(0, len(sums), size=(RESAMPLES, len(sums)))
    session_means = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
    return {"mean": float(values.mean()), "cases": percentile_interval(case_means),
            "sessions": percentile_interval(session_means)}


def percentile_interval(means: np.ndarray) -> list[float]:
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def width_ratio(stat: dict[str, Any]) -> float:
    case = stat["cases"][1] - stat["cases"][0]
    return (stat["sessions"][1] - stat["sessions"][0]) / case if case else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("test-split", "eb-rows", "eb-summary", "f-rows", "f-summary", "out"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    test = json.loads(args.test_split.read_text(encoding="utf-8"))
    rng = np.random.default_rng(20261030)
    out: dict[str, Any] = {}

    # E-B confirmation sample (Table 1)
    rows = json.loads(args.eb_rows.read_text(encoding="utf-8"))
    reported = json.loads(args.eb_summary.read_text(encoding="utf-8"))["results"]["all"]
    sessions = [session_key(test[r["index"]]) for r in rows]
    eb: dict[str, Any] = {"cases": len(rows), "sessions": len(set(sessions))}
    methods = list(rows[0]["scores"])
    for method in methods:
        values = np.array([r["scores"][method] for r in rows], dtype=float)
        for j, metric in enumerate(METRICS):
            stat = intervals(values[:, j], sessions, rng)
            stat["reported"] = reported[method][metric][0]
            eb[f"{method} {metric}"] = stat
    m5 = next(m for m in methods if m.startswith("M5"))
    for other in ("M1 nearest", "M2 most check-ins", next(m for m in methods if m.startswith("M4"))):
        for j, metric in enumerate(METRICS):
            diff = np.array([r["scores"][m5][j] - r["scores"][other][j] for r in rows])
            eb[f"{m5.split()[0]} - {other.split()[0]} {metric}"] = intervals(diff, sessions, rng)
    out["E-B"] = eb

    # E-F
    rows = json.loads(args.f_rows.read_text(encoding="utf-8"))
    reported = json.loads(args.f_summary.read_text(encoding="utf-8"))
    sessions = [session_key(test[r["index"]]) for r in rows]
    ef: dict[str, Any] = {"cases": len(rows), "sessions": len(set(sessions))}
    for name in ("B", "P", "R"):
        for metric in ("hr1", "hr5", "hr10", "ndcg10"):
            stat = intervals(np.array([r[f"{name} {metric}"] for r in rows]), sessions, rng)
            stat["reported"] = reported["accuracy"][name][metric][0]
            ef[f"{name} {metric}"] = stat
    for a, b in (("P", "B"), ("R", "P")):
        diff = np.array([r[f"{a} hr10"] - r[f"{b} hr10"] for r in rows])
        ef[f"HR@10 {a} - {b}"] = intervals(diff, sessions, rng)
    for metric in ("repeat", "same_as_last", "hop_km"):
        for name in ("P", "R"):
            stat = intervals(np.array([r[f"{name} {metric}"] for r in rows]), sessions, rng)
            stat["reported"] = reported["routes"][name][metric][0]
            ef[f"{name} {metric}"] = stat
        diff = np.array([r[f"R {metric}"] - r[f"P {metric}"] for r in rows])
        ef[f"R - P {metric}"] = intervals(diff, sessions, rng)
    diff = np.array([r["R hop_km"] - r["P hop_km"] for r in rows])
    ef["R - P route mean hop, median of the paired differences"] = float(np.median(diff))
    ef["R - P route mean hop, share of routes shorter / longer"] = [
        float(np.mean(diff < -1e-9)), float(np.mean(diff > 1e-9))]
    for name in ("P", "R"):
        hops = np.array([h for r in rows for h in r[f"{name} hops"]])
        ef[f"{name} hop median km"] = float(np.median(hops))
        ef[f"{name} hops over 2 km"] = float(np.mean(hops > 2.0))
    out["E-F"] = ef

    ratios = [width_ratio(v) for part in out.values() for v in part.values()
              if isinstance(v, dict) and "sessions" in v]
    out["session / case interval width"] = {"median": float(np.median(ratios)),
                                            "max": float(np.max(ratios))}
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")

    def show(label: str, stat: dict[str, Any]) -> None:
        c, s = stat["cases"], stat["sessions"]
        rep = f"  reported {stat['reported']:.3f}" if "reported" in stat else ""
        print(f"{label:44}{stat['mean']:+.3f}  cases [{c[0]:+.3f}, {c[1]:+.3f}]"
              f"  sessions [{s[0]:+.3f}, {s[1]:+.3f}]{rep}")

    for part, values in out.items():
        print(f"\n{part}")
        for label, stat in values.items():
            if isinstance(stat, dict) and "sessions" in stat:
                show(label, stat)
            else:
                print(f"{label:44}{stat}")


if __name__ == "__main__":
    main()
