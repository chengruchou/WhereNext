"""Route explanations written from the route evidence and checked sentence by sentence.

Claude sees only the evidence JSON and returns a GroundedExplanation in which
every sentence cites evidence paths. The verifier then checks each sentence;
the Markdown shown to the user keeps supported and unverifiable sentences,
drops unsupported ones, and says how many of each there were.
"""

from __future__ import annotations

import json
import os
from typing import Any

from contracts.evidence import GroundedExplanation, RouteEvidence, VerifiedExplanation
from services.explanation_verifier import verify_explanation


DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
You explain a recommended route to a traveler. The user message is the route evidence as JSON: \
the traveler's past visits (history), their request (intent, may be null), the weights used \
(controls), and one record per stop (steps) with its scored signals, distance from the previous \
stop (travel), and how often the traveler visited that place type (history).

Signals: habit = fits the traveler's past sequence; semantic_history = similar to past visits; \
geo = close by; intent = similar to the request; novelty = new for this traveler; travel = \
travel cost; repeat = repeats a place type already in the route. A signal's contribution is its \
share of the stop's final_score; top_signal names the largest.

A stop whose intent.matched_want is not empty is one of the requested place types. When \
intent.in_range is 0, the data has no place of the requested types within \
intent.search_radius_km km of the previous stop, so that stop follows the traveler's habits.

Rules:
- Say only what the evidence shows. For every sentence, list in evidence_refs the JSON paths it \
relies on, 0-based, such as "steps[0].travel.distance_km", "steps[1].intent.matched_want", \
"steps[2].history.same_category_visits" or "history[2].category_name".
- Write for the traveler, not for an engineer. Do not quote scores, weights, signal values or \
contributions, and do not use the signal names; say what they mean instead ("you often go to \
coffee shops", "it is one of the museums you asked for", "it is a short walk from the last stop").
- The only numbers to use are distances and visit counts. Copy them from the values you cite: \
kilometres with at most two decimals. Do not convert units.
- Name place types exactly as the evidence spells them, and only ones you cite.
- The data has no ratings, reviews, prices, opening hours or crowd levels. Never mention them.
- Write one summary sentence about the whole route, then exactly one sentence per stop, each at \
most 25 words.
"""


def request_explanation(client: Any, evidence_json: dict[str, Any]) -> Any:
    """Ask Claude for a GroundedExplanation; the caller handles SDK errors."""

    return client.beta.messages.parse(
        model=os.getenv("WHERENEXT_EXPLAIN_MODEL", DEFAULT_MODEL),
        max_tokens=16000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": json.dumps(evidence_json, ensure_ascii=False)}],
        output_format=GroundedExplanation,
        # Citing paths correctly takes some care; medium is the model's default effort.
        output_config={"effort": "medium"},
        # If a safety classifier declines, the API retries on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )


def evidence_for_prompt(evidence: RouteEvidence) -> dict[str, Any]:
    """The evidence the explanation may cite; stage timings are left out."""

    return evidence.model_dump(mode="json", exclude={"stages"})


def explain(
    explanation: GroundedExplanation,
    evidence_json: dict[str, Any],
    categories: list[str],
) -> tuple[VerifiedExplanation, str]:
    verified = verify_explanation(explanation, evidence_json, categories)
    return verified, render_markdown(verified, evidence_json)


def render_markdown(verified: VerifiedExplanation, evidence_json: dict[str, Any]) -> str:
    kept: dict[tuple[int | None, int], bool] = {
        (v.step, v.index): v.verdict != "unsupported" for v in verified.verdicts
    }
    counts = {"supported": 0, "unverifiable": 0, "unsupported": 0}
    for v in verified.verdicts:
        counts[v.verdict] += 1

    explanation = verified.explanation
    lines = ["### Overall Route Summary"]
    summary = [s.text for i, s in enumerate(explanation.summary) if kept.get((None, i))]
    lines.append(" ".join(summary) if summary else "_No summary sentence passed the check._")

    steps = evidence_json.get("steps", [])
    for step in explanation.steps:
        sentences = [s.text for i, s in enumerate(step.sentences) if kept.get((step.step, i))]
        if not sentences:
            continue
        poi = steps[step.step - 1]["poi"] if 0 < step.step <= len(steps) else {}
        header = f"**Step {step.step}: {(poi.get('category_name') or 'Stop').strip()}**"
        if poi.get("raw_poi_id") is not None:
            header += f" `({poi['raw_poi_id']})`"
        lines.extend(["", header, " ".join(sentences)])

    lines.extend(
        [
            "",
            "---",
            f"_Checked against this route's evidence: {counts['supported']} supported, "
            f"{counts['unverifiable']} not checkable, {counts['unsupported']} removed as "
            "unsupported._",
        ]
    )
    return "\n".join(lines)
