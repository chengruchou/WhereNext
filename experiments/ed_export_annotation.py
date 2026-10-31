"""E-D: export Claude's explanation sentences for the annotators, without the verdicts.

Writes experiments/<batch>_annotation/sentences.csv (what annotators see, in a shuffled order) and
key.csv (the verifiers' verdicts, opened only after every annotator has labelled). Each row shows
the whole route, so a sentence about another stop ("a longer drive", "from the Apple Store")
can be judged from the row.

    python experiments/ed_export_annotation.py <results.json> <batch>

E-D2 comes from experiments/results/claude_validate_2026-10-30.json, E-D from
experiments/results/claude_batch_2026-10-30.json.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from contracts.evidence import (
    ExplanationSentence,
    GroundedExplanation,
    StepExplanation,
    resolve_ref,
)
from services.explanation_verifier import VERIFIER_VERSION, verify_explanation
from services.intent_parser import CategoryVocabulary
from services.model_config import RecommendationConfig

SIGNAL_NAMES = {"intent": "request", "habit": "habit", "novelty": "novelty"}


def short(value: Any, limit: int = 120) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[: limit - 1] + "…"


def name(poi: dict[str, Any]) -> str:
    return (poi["category_name"] or "?").strip()


def request_text(intent: dict[str, Any]) -> str:
    want = ", ".join(m["category_name"].strip() for m in intent.get("want", []))
    avoid = ", ".join(m["category_name"].strip() for m in intent.get("avoid", []))
    parts = [f"want: {want or '-'}", f"avoid: {avoid or '-'}", f"mode: {intent['travel_mode']}",
             f"novelty: {intent['explore']}"]
    return "; ".join(parts)


def stop_line(step: dict[str, Any], start: str, asked: bool) -> str:
    """One stop of the route, with every fact the explanation could draw on."""
    match = step.get("intent") or {}
    travel = step.get("travel") or {}
    history = step["history"]
    n = step["step"]
    origin = f"your last visit ({start})" if n == 1 else f"stop {n - 1}"
    km = travel.get("distance_km")
    facts = [f"{n}. {name(step['poi'])}",
             f"{km:.2f} km from {origin}" if km is not None else f"? km from {origin}"]
    if asked:
        facts.append("requested type" if match.get("matched_want") else "not requested")
    if match.get("in_range") is not None:
        facts.append(f"requested places within {match.get('search_radius_km', '?'):g} km: "
                     f"{match['in_range']}")
    facts += [(f"type seen before: {history['same_category_visits']} of "
               f"{history['history_window']} earlier visits"),
              f"been to this place: {'yes' if history['visited_this_poi'] else 'no'}",
              f"place {step['poi']['raw_poi_id']}",
              f"main signal: {SIGNAL_NAMES.get(step['top_signal'], step['top_signal'])}",
              f"habit score {step['signals']['habit']['value']:.2f}"]
    return " · ".join(facts)


def route_text(ev: dict[str, Any], step: int | None, asked: bool) -> str:
    """Every stop on its own line; the stop the sentence is about is marked with ▶."""
    start = name(ev["history"][-1])
    return "\n".join(("▶ " if s["step"] == step else "   ") + stop_line(s, start, asked)
                     for s in ev["steps"])


def verify_again(route: dict[str, Any], categories: list[str]) -> list[Any]:
    """The current verifier's verdicts for the route's saved sentences, in their order."""
    sentences = route["sentences"]
    summary = [ExplanationSentence(text=s["text"], evidence_refs=s["refs"])
               for s in sentences if s["step"] is None]
    steps: dict[int, list[ExplanationSentence]] = {}
    for s in sentences:
        if s["step"] is not None:
            steps.setdefault(s["step"], []).append(
                ExplanationSentence(text=s["text"], evidence_refs=s["refs"]))
    explanation = GroundedExplanation(
        summary=summary,
        steps=[StepExplanation(step=k, sentences=v) for k, v in steps.items()])
    verified = verify_explanation(explanation, route["evidence"], categories)
    by_key = {(v.step, v.index): v for v in verified.verdicts}
    seen: dict[int | None, int] = {}
    out = []
    for s in sentences:
        i = seen.get(s["step"], 0)
        seen[s["step"]] = i + 1
        out.append(by_key[(s["step"], i)])
    return out


def main() -> None:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    batch = sys.argv[2]
    out = Path(__file__).resolve().parent / f"{batch}_annotation"
    categories = CategoryVocabulary.from_metadata(
        RecommendationConfig.from_env().poi_metadata_path).names
    rows, key = [], []
    for r, route in enumerate(data[batch], start=1):
        ev = route["evidence"]
        history = " → ".join(name(p) for p in ev["history"])
        now = verify_again(route, categories)
        for s, v in zip(route.get("sentences", []), now, strict=True):
            cited = []
            for ref in s["refs"]:
                try:
                    cited.append(f"{ref} = {short(resolve_ref(ev, ref))}")
                except KeyError:
                    cited.append(f"{ref} = (no such path)")
            step = s["step"]
            rows.append({
                "route": r, "request": request_text(route["intent"]),
                "history": history, "step": "summary" if step is None else step,
                "route stops": route_text(ev, step, bool(route["intent"].get("want"))),
                "sentence": s["text"], "cited values": " | ".join(cited),
            })
            # The E-D batch saved verifier/2.1 as v2; E-D2 saved it as v2.1.
            key.append({VERIFIER_VERSION: v.verdict, f"{VERIFIER_VERSION} reason": v.reason or "",
                        "verifier/2.1": s.get("v2.1", s["v2"]),
                        "verifier/2.1 reason": s.get("v2.1_reason", s["v2_reason"]) or "",
                        "verifier/1": s["v1"], "verifier/1 reason": s["v1_reason"] or ""})
    order = list(range(len(rows)))
    random.Random(20).shuffle(order)
    out.mkdir(exist_ok=True)
    fields = ["id", *rows[0], "annotator label", "misleading", "note"]
    with open(out / "sentences.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for n, i in enumerate(order, start=1):
            writer.writerow({"id": n, **rows[i], "annotator label": "", "misleading": "",
                             "note": ""})
    with open(out / "key.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", *key[0]], lineterminator="\n")
        writer.writeheader()
        for n, i in enumerate(order, start=1):
            writer.writerow({"id": n, **key[i]})
    print(f"{len(rows)} sentences from {len(data[batch])} routes written to {out}")


if __name__ == "__main__":
    main()
