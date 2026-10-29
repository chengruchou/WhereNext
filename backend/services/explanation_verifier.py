"""Check each explanation sentence against the route evidence it cites.

A sentence is supported only if every path it cites exists in the evidence,
every number it states matches a cited value (after the rounding the sentence
shows, and with 0.8 read as 80%), every place type it names is among the cited
values, and it claims no attribute the data does not contain, such as ratings,
prices or opening hours. A sentence that cites real paths but states no number
and no place type is unverifiable: nothing in it can be checked.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from contracts.evidence import (
    ExplanationSentence,
    GroundedExplanation,
    SentenceVerdict,
    VerifiedExplanation,
    resolve_ref,
)


VERIFIER_VERSION = "verifier/1"

_ABSENT_ATTRIBUTES = re.compile(
    r"\b(rated|ratings?|stars?|reviews?|prices?|cheap|expensive|affordable|opening hours|"
    r"open late|open now|crowded|quiet|famous|award[- ]winning|highly)\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(\s*%)?")
_STEP_LABEL = re.compile(r"\b(?:step|stop)\s+\d+\b", re.IGNORECASE)


def verify_explanation(
    explanation: GroundedExplanation,
    evidence: dict[str, Any],
    categories: list[str],
) -> VerifiedExplanation:
    """Verify every sentence; evidence is the JSON the explanation was written from."""

    names = sorted({c.strip() for c in categories if c and c.strip()}, key=len, reverse=True)
    verdicts = [
        verify_sentence(sentence, evidence, names, step=None, index=index)
        for index, sentence in enumerate(explanation.summary)
    ]
    for step in explanation.steps:
        verdicts.extend(
            verify_sentence(sentence, evidence, names, step=step.step, index=index)
            for index, sentence in enumerate(step.sentences)
        )
    return VerifiedExplanation(
        explanation=explanation, verdicts=verdicts, verifier_version=VERIFIER_VERSION
    )


def verify_sentence(
    sentence: ExplanationSentence,
    evidence: dict[str, Any],
    category_names: list[str],
    *,
    step: int | None,
    index: int,
) -> SentenceVerdict:
    def verdict(kind: str, reason: str | None = None) -> SentenceVerdict:
        return SentenceVerdict(step=step, index=index, verdict=kind, reason=reason)

    cited: list[Any] = []
    for ref in sentence.evidence_refs:
        try:
            cited.append(resolve_ref(evidence, ref))
        except KeyError:
            return verdict("unsupported", f"cites a path that does not exist: {ref}")

    text = sentence.text
    absent = _ABSENT_ATTRIBUTES.search(text)
    if absent:
        return verdict(
            "unsupported", f'claims "{absent.group(0)}", which the data does not contain'
        )

    leaves = list(_leaves(cited))
    numbers = [float(v) for v in leaves if isinstance(v, (int, float)) and not isinstance(v, bool)]
    strings = {v.strip().casefold() for v in leaves if isinstance(v, str)}

    checked = False
    named, rest = _named_categories(text, category_names)
    for name in named:
        if name.casefold() not in strings:
            return verdict(
                "unsupported", f"names {name}, which the cited evidence does not mention"
            )
        checked = True

    # Numbers inside place-type names ("24 Hour Fitness") and step labels are not claims.
    for match in _NUMBER.finditer(_STEP_LABEL.sub(" ", rest)):
        if not _number_supported(match.group(1), bool(match.group(2)), numbers):
            return verdict(
                "unsupported", f"states {match.group(0).strip()}, which no cited value supports"
            )
        checked = True

    if not checked:
        return verdict("unverifiable", "states no number or place type to check")
    return verdict("supported")


def _leaves(value: Any) -> Iterator[Any]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _leaves(item)
    else:
        yield value


def _number_supported(token: str, percent: bool, cited: list[float]) -> bool:
    value = float(token)
    decimals = len(token.split(".")[1]) if "." in token else 0
    tolerance = 0.5 * 10**-decimals + 1e-9
    for number in cited:
        if abs(number - value) <= tolerance:
            return True
        if percent and abs(number * 100 - value) <= tolerance:
            return True
    return False


def _named_categories(text: str, category_names: list[str]) -> tuple[list[str], str]:
    """Place types the text names, longest first so "History Museum" is not also "Museum",
    and the text with those names removed."""

    remaining = text
    found = []
    for name in category_names:
        pattern = re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])", re.IGNORECASE)
        if pattern.search(remaining):
            found.append(name)
            remaining = pattern.sub(" ", remaining)
    return found, remaining
