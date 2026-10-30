"""E-D: export Claude's explanation sentences for the two annotators, without the verdicts.

Writes experiments/E-D_annotation/sentences.csv (what annotators see, in a shuffled order) and
key.csv (the verifiers' verdicts, opened only after both have labelled).

    python experiments/ed_export_annotation.py experiments/results/claude_batch_2026-10-30.json
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from contracts.evidence import resolve_ref

OUT = Path(__file__).resolve().parent / "E-D_annotation"


def short(value: Any, limit: int = 120) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[: limit - 1] + "…"


def request_text(intent: dict[str, Any]) -> str:
    want = ", ".join(m["category_name"].strip() for m in intent.get("want", []))
    avoid = ", ".join(m["category_name"].strip() for m in intent.get("avoid", []))
    parts = [f"want: {want or '-'}", f"avoid: {avoid or '-'}", f"mode: {intent['travel_mode']}",
             f"novelty: {intent['explore']}"]
    return "; ".join(parts)


def stop_facts(step: dict[str, Any]) -> str:
    match = step.get("intent") or {}
    travel = step.get("travel") or {}
    history = step["history"]
    facts = [f"type: {(step['poi']['category_name'] or '?').strip()}",
             f"km from previous: {travel.get('distance_km', '?'):.2f}"
             if travel.get("distance_km") is not None else "km from previous: ?",
             (f"visits of this type: {history['same_category_visits']} of the last "
              f"{history['history_window']}")]
    if match:
        facts.append("a requested type" if match.get("matched_want") else "not a requested type")
        if match.get("in_range") is not None:
            facts.append(f"requested places within {match.get('search_radius_km', '?'):g} km: "
                         f"{match['in_range']}")
    return "; ".join(facts)


def main() -> None:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    rows, key = [], []
    for r, route in enumerate(data["E-D"], start=1):
        ev = route["evidence"]
        history = " → ".join((p["category_name"] or "?").strip() for p in ev["history"])
        for s in route.get("sentences", []):
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
                "stop facts": stop_facts(ev["steps"][step - 1]) if step else "",
                "sentence": s["text"], "cited values": " | ".join(cited),
            })
            key.append({"verifier/2.1": s["v2"], "verifier/2.1 reason": s["v2_reason"] or "",
                        "verifier/1": s["v1"], "verifier/1 reason": s["v1_reason"] or ""})
    order = list(range(len(rows)))
    random.Random(20).shuffle(order)
    OUT.mkdir(exist_ok=True)
    fields = ["id", *rows[0], "annotator label", "note"]
    with open(OUT / "sentences.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for n, i in enumerate(order, start=1):
            writer.writerow({"id": n, **rows[i], "annotator label": "", "note": ""})
    with open(OUT / "key.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", *key[0]], lineterminator="\n")
        writer.writeheader()
        for n, i in enumerate(order, start=1):
            writer.writerow({"id": n, **key[i]})
    print(f"{len(rows)} sentences from {len(data['E-D'])} routes written to {OUT}")


if __name__ == "__main__":
    main()
