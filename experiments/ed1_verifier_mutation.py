"""E-D1: the explanation verifier on sentences whose truth is known by construction.

Design and predictions, written before this ran: experiments/E-D1_verifier_mutation.md.
Route evidence is built offline as /route builds it, with the test case's history in place
of the database lookup; no external API is called.

    python experiments/ed1_verifier_mutation.py --test-split <path> --split dev --out dev.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from contracts.evidence import (
    ExplanationSentence,
    GroundedExplanation,
    RouteEvidence,
    StepExplanation,
)
from contracts.intent import CategoryMatch, Intent
from offline_suite import Setup
from services.evidence_builder import build_step_records, poi_facts
from services.explanation_verifier import VERIFIER_VERSION, verify_explanation
from services.grounded_explainer import evidence_for_prompt
from services.intent_parser import CategoryVocabulary, controls_for
from services.recommendation_service import _extract_raw_poi_id

MODES = ("walk", "transit", "drive")
WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
         9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}
PRAISE = ("popular with locals", "the best {cat} in town", "a lively spot")
METADATA = Path(__file__).resolve().parents[1] / "backend" / "datasets" / "filtered_poi_metadata.json"


class OfflineRoutes:
    """Builds RouteEvidence like RecommendationService.recommend_route, minus the database."""

    def __init__(self, setup: Setup):
        self.setup = setup
        self.service = setup.base
        self.meta = json.loads(METADATA.read_text(encoding="utf-8"))

    def _poi(self, raw_id: int) -> dict[str, Any] | None:
        return self.meta.get(str(raw_id))

    def _hydrate(self, rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        ranked, seen = [], set()
        for row in rows:
            raw_id = _extract_raw_poi_id(row)
            poi = self._poi(raw_id) if raw_id is not None else None
            if raw_id in seen or poi is None or poi.get("category_name") == "":
                continue
            seen.add(raw_id)
            ranked.append((row, poi))
        return ranked

    def evidence(self, history: list[int], intent: Intent, stops: int = 3) -> dict[str, Any]:
        controls = controls_for(intent, self.service.config)
        chosen: list[int] = []
        steps = []
        start: list[dict[str, Any]] | None = None
        for step in range(1, stops + 1):
            raw_ids = history + chosen
            session = [p for p in map(self._poi, raw_ids) if p is not None]
            start = session if start is None else start
            rows, _, steering_ran = self.service.rank_session(
                raw_ids, step=step, intent=intent, controls=controls, route_stops=list(chosen)
            )
            ranked = self._hydrate(rows)
            if not ranked:
                break
            records = build_step_records(
                ranked, step=step, pool=rows, session=session, config=self.service.config,
                controls=controls if steering_ran else None, travel_mode=intent.travel_mode,
            )
            steps.append(records[0])
            chosen.append(int(ranked[0][1]["raw_poi_id"]))
        evidence = RouteEvidence(
            request_id="offline", user_id=0, dataset="gowalla", backbone="MG-DSGAT",
            history=[poi_facts(p) for p in start or []], intent=intent, controls=controls,
            steps=steps, stages=[],
        )
        return evidence_for_prompt(evidence)


def request(setup: Setup, case: dict[str, Any], mode: str) -> Intent:
    """Want the next place's type; avoid the history's most frequent other type."""
    want = case["category"]
    raw = [setup.index.points[r].category for r in case["history"] if r in setup.index.points]
    counts = Counter(c.strip() for c in raw if c and c.strip())
    avoid = []
    top = counts.most_common(1)
    if top and top[0][0] != want.strip():
        spelled = next(c for c in raw if c and c.strip() == top[0][0])
        avoid = [CategoryMatch(category_name=spelled, phrase=top[0][0].lower(),
                               method="user_edit")]
    return Intent(
        query=f"a {want.strip().lower()}", source="user_edit", strength="soft",
        want=[CategoryMatch(category_name=want, phrase=want.strip().lower(), method="user_edit")],
        avoid=avoid, travel_mode=mode,
    )


def _strings(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_strings(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_strings(v) for v in value)) if value else set()
    return {value.strip().casefold()} if isinstance(value, str) else set()


def sentences(ev: dict[str, Any], vocabulary: list[str], rng: random.Random):
    """Yield (family, step or None, text, refs); step is 1-based, None for the summary."""
    steps, history, intent = ev["steps"], ev["history"], ev["intent"]
    avoid = intent["avoid"][0]["category_name"].strip() if intent and intent["avoid"] else None
    in_route = _strings(ev)

    if history and (history[-1]["category_name"] or "").strip():
        last = len(history) - 1
        yield ("T6", None, f"Your last visit was a {history[last]['category_name'].strip()}.",
               [f"history[{last}].category_name"])
    if steps and steps[0]["travel"]:
        yield ("T7", None, (f"The route starts {steps[0]['travel']['distance_km']:.2f} km from "
               "your last visit."), ["steps[0].travel.distance_km"])

    for i, s in enumerate(steps):
        k, p = s["step"], f"steps[{i}]"
        cat = (s["poi"]["category_name"] or "").strip()
        if not cat:
            continue
        d = s["travel"]["distance_km"] if s["travel"] else None
        n, w = s["history"]["same_category_visits"], s["history"]["history_window"]
        match = s["intent"] or {}
        matched = bool(match.get("matched_want"))
        cat_ref, d_ref = f"{p}.poi.category_name", f"{p}.travel.distance_km"
        n_ref, w_ref = f"{p}.history.same_category_visits", f"{p}.history.history_window"

        # T: true, written as the explainer is told to write
        if d is not None:
            yield ("T1", k, f"It is {d:.2f} km from the previous stop.", [d_ref])
        if matched:
            yield ("T2", k, f"It is a {cat}, one of the place types you asked for.",
                   [cat_ref, f"{p}.intent.matched_want"])
        if n > 0:
            yield ("T3", k, f"You visited {cat} places {n} times in your last {w} visits.",
                   [cat_ref, n_ref, w_ref])
        else:
            yield ("T3", k, f"A {cat} is new to you: none of your last {w} visits were one.",
                   [cat_ref, n_ref, w_ref])
        if match.get("in_range") == 0 and match.get("search_radius_km"):
            yield ("T4", k, (f"No place of the requested types is within "
                   f"{match['search_radius_km']:g} km of the previous stop, so this stop follows "
                   "your habits."), [f"{p}.intent.in_range", f"{p}.intent.search_radius_km"])
        if avoid:
            yield ("T5", k, f"It is a {cat}, not a {avoid}, as you asked.",
                   [cat_ref, "intent.avoid[0].category_name"])

        # P: true, phrased against the explainer's rules or under-cited
        if d is not None:
            yield ("P1", k, f"It is {d * 1000:.0f} m from the previous stop.", [d_ref])
            yield ("P2", k, f"It is about {d:.1f} km away.", [d_ref])
            yield ("P4", k, f"The {ORDINALS[k]} stop is {d:.2f} km from the one before.", [d_ref])
        if matched and not cat.endswith("s"):
            yield ("P3", k, f"It is one of the {cat.lower()}s you asked for.",
                   [cat_ref, f"{p}.intent.matched_want"])
        if n in WORDS:
            yield ("P5", k, f"You visited {cat} places {WORDS[n]} times recently.",
                   [cat_ref, n_ref])
        if 0 < n != w:
            yield ("P6", k, f"{n} of your last {w} visits were {cat} places.", [cat_ref, n_ref])
        if avoid:
            yield ("P7", k, f"It is a {cat} instead of another {avoid}.", [cat_ref])
        if n == 0:
            yield ("P8", k, f"It is a {cat}, new to you.", [cat_ref])

        # M: false by construction
        if d is not None:
            yield ("M1", k, f"It is {d + max(0.5, d):.2f} km from the previous stop.", [d_ref])
            yield ("M4a", k, f"It is {d:.2f} km from the previous stop and is highly rated.",
                   [d_ref])
            praise = PRAISE[(i + k) % len(PRAISE)].format(cat=cat)
            yield ("M4b", k, f"It is {d:.2f} km from the previous stop and {praise}.",
                   [d_ref, cat_ref])
            yield ("M5", k, f"It is {d:.2f} km from the previous stop.",
                   [d_ref, f"{p}.poi.rating"])
            if d >= 0.01:
                yield ("M8", k, f"It is {d:.2f} miles from the previous stop.", [d_ref])
            others = [j for j, o in enumerate(steps)
                      if j != i and o["travel"] and abs(o["travel"]["distance_km"] - d) > 0.01]
            if others:
                j = others[0]
                yield ("M6", k, (f"It is {steps[j]['travel']['distance_km']:.2f} km from the "
                       "previous stop."), [f"steps[{j}].travel.distance_km"])
        yield ("M2", k, f"You visited {cat} places {n + 2} times in your last {w} visits.",
               [cat_ref, n_ref, w_ref])
        wrong = [c for c in vocabulary if c.casefold() not in in_route
                 and c.casefold() not in cat.casefold() and cat.casefold() not in c.casefold()]
        yield ("M3", k, f"It is a {rng.choice(wrong)}.", [cat_ref])
        yield ("M7", k, f"It is not a {cat}.", [cat_ref])
        counts = {n, w, match.get("in_range")} | {s["poi"].get(f) for f in
                                                  ("checkins_count", "users_count", "photos_count")}
        decoys = [x for x in (s["rank"], s["pool_size"], s["step"]) if x not in counts]
        if decoys:
            yield ("M9", k, f"You visited {cat} places {decoys[0]} times before.", [p])
        yield ("M10", k, f"It is the closest {cat} to your last stop.", [cat_ref, d_ref])
        if avoid:
            yield ("M11", k, f"This stop is a {avoid}.", ["intent.avoid[0].category_name"])
        if n == 0:
            yield ("M12", k, f"You often visit {cat} places.", [cat_ref, n_ref])
        else:
            yield ("M13", k, f"A {cat} is new to you.", [cat_ref, n_ref])


def verdict(ev: dict[str, Any], categories: list[str], step: int | None, text: str,
            refs: list[str]):
    sentence = ExplanationSentence(text=text, evidence_refs=refs)
    filler = ExplanationSentence(text="Placeholder.", evidence_refs=["dataset"])
    if step is None:
        explanation = GroundedExplanation(summary=[sentence], steps=[])
        key = (None, 0)
    else:
        explanation = GroundedExplanation(
            summary=[filler], steps=[StepExplanation(step=step, sentences=[sentence])])
        key = (step, 0)
    verified = verify_explanation(explanation, ev, categories)
    return next(v for v in verified.verdicts if (v.step, v.index) == key)


def draw(setup: Setup, n: int, seed: int, exclude: set[int]) -> list[dict[str, Any]]:
    cases, _ = setup.new_place_cases(n + len(exclude), seed)
    return [c for c in cases if c["index"] not in exclude][:n]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test-split", required=True, type=Path)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--cases", type=int, default=150)
    parser.add_argument("--dev-seed", type=int, default=12)
    parser.add_argument("--test-seed", type=int, default=13)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    setup = Setup(args.test_split)
    routes = OfflineRoutes(setup)
    categories = CategoryVocabulary.from_metadata(setup.config.poi_metadata_path).names
    vocabulary = sorted({c.strip() for c in categories if c.strip()})

    dev = draw(setup, args.cases, args.dev_seed, set())
    cases = dev if args.split == "dev" else draw(
        setup, args.cases, args.test_seed, {c["index"] for c in dev})

    rng = random.Random(args.dev_seed if args.split == "dev" else args.test_seed)
    rows = []
    for j, case in enumerate(cases):
        ev = routes.evidence(case["history"], request(setup, case, MODES[j % 3]))
        for family, step, text, refs in sentences(ev, vocabulary, rng):
            v = verdict(ev, categories, step, text, refs)
            rows.append({"case": case["index"], "family": family, "step": step, "text": text,
                         "refs": refs, "verdict": v.verdict, "reason": v.reason})

    table: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        table[row["family"]][row["verdict"]] += 1
    order = sorted(table, key=lambda f: (f[0] != "T", f[0] != "P", int(f[1:].rstrip("ab")), f))
    summary = {}
    print(f"{VERIFIER_VERSION}, {args.split}, {len(cases)} routes")
    print(f"{'family':7}{'n':>6}{'removed':>9}{'checked':>9}{'not checkable':>15}")
    for family in order:
        c = table[family]
        total = sum(c.values())
        summary[family] = {"n": total, "removed": c["unsupported"] / total,
                           "checked": c["supported"] / total,
                           "not_checkable": c["unverifiable"] / total}
        print(f"{family:7}{total:6d}{summary[family]['removed']:9.1%}"
              f"{summary[family]['checked']:9.1%}{summary[family]['not_checkable']:15.1%}")
    args.out.write_text(json.dumps({"verifier": VERIFIER_VERSION, "split": args.split,
                                    "routes": len(cases), "summary": summary, "rows": rows},
                                   indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
