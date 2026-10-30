"""Check each explanation sentence against the route evidence it cites.

A sentence is supported only if every path it cites exists in the evidence and
every claim it makes that the verifier can read holds:

- each number matches a cited value of the right kind after the rounding the
  sentence shows: km, m and miles against distances in km, a share in % against
  a fraction, "N times" against visit counts; a stop's sentence may not take its
  numbers from another stop;
- each place type it names is cited or appears in the route's history or
  request, and a stop is never said to be a type it is not;
- "often", "new to you" and the like agree with the history's visit counts;
- it claims no attribute the data does not contain (ratings, prices, opening
  hours, popularity) and no comparison it cannot show ("the closest").

A sentence that cites real paths but makes none of these claims is
unverifiable: nothing in it can be checked.
"""

from __future__ import annotations

import functools
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


VERIFIER_VERSION = "verifier/2.2"

_ABSENT_ATTRIBUTES = re.compile(
    r"\b(rated|ratings?|stars?|reviews?|reviewed|prices?|priced|cheap|expensive|affordable|"
    r"opening hours|open late|open now|crowded|crowds?|busy|quiet|lively|famous|popular|"
    r"popularity|well[- ]known|award[- ]winning|top[- ]rated|highly recommended|must[- ]see|"
    r"iconic|hidden gem|beloved|locals|trendy|delicious|tasty|friendly|cozy|cosy|beautiful|"
    r"stunning|scenic)\b",
    re.IGNORECASE,
)
_COMPARISON = re.compile(
    r"\b(closest|nearest|farthest|furthest|best|worst|biggest|largest|smallest|highest|"
    r"lowest)\b",
    re.IGNORECASE,
)
# A claim that the traveler goes to a type often: a frequency word with a visiting verb, or
# "favourite". "The way you usually move" describes habit in general and is not read as one.
_OFTEN = re.compile(
    r"\b(?:often|usually|regularly|frequently|always)\s+(?:go|goes|went|visit|visits|visited|"
    r"stop|stops|head|heads|choose|chooses|pick|picks|eat|drink)\b"
    r"|\b(?:go|goes|went|visit|visits|visited)\b[^.;]{0,40}\b(?:often|regularly|a lot)\b"
    r"|\bfavou?rite\b",
    re.IGNORECASE,
)
_NEW = re.compile(
    r"\b(new to you|never|first time|have not been|haven't been|none of your)\b", re.IGNORECASE
)
# "You have not been to this place" is about the place itself, not its type.
_THIS_PLACE = re.compile(r"\b(?:this|that) (?:place|spot|one)\b|\bhere\b", re.IGNORECASE)
# Where a clause ends, so "often" and "new to you" are read with the types in their own clause.
_CLAUSE_BREAK = re.compile(r"[,;:]|\b(?:and|but|then|so|while|which|where)\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:not|no|never|isn't|aren't|wasn't)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)
# "It is a", "This stop is not a": what follows is said to be the stop itself.
_IDENTITY = re.compile(
    r"\b(?:it|this(?:\s+(?:stop|place))?|the\s+(?:\w+\s+)?stop|stop\s+\d+)\s+(?:is|was|'s)\s+"
    r"(?:not\s+)?(?:a|an|another|the)?\s*$",
    re.IGNORECASE,
)
_STEP_LABEL = re.compile(r"\b(?:step|stop)\s+\d+\b|\b\d+(?:st|nd|rd|th)\b", re.IGNORECASE)
_NUMBER = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)(?:\s*(%|km|kilomet(?:er|re)s?|m|met(?:er|re)s?|mi|miles?|"
    r"times|visits?|check-ins?)(?![\w-]))?",
    re.IGNORECASE,
)
_NUMBER_WORDS = {"twice": 2, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_NUMBER_WORD = re.compile(
    rf"\b({'|'.join(_NUMBER_WORDS)})\b(?:\s+(times|visits?|check-ins?))?", re.IGNORECASE
)
KM_PER_MILE = 1.609344
_KM_KEYS = ("distance_km", "search_radius_km", "max_hop_km")
# unit as written: (cited fields it may be read from, factor from that field's value)
_UNITS: dict[str, tuple[tuple[str, ...] | None, float]] = {
    **dict.fromkeys(("km", "kilometer", "kilometers", "kilometre", "kilometres"), (_KM_KEYS, 1.0)),
    **dict.fromkeys(("m", "meter", "meters", "metre", "metres"), (_KM_KEYS, 1000.0)),
    **dict.fromkeys(("mi", "mile", "miles"), (_KM_KEYS, 1 / KM_PER_MILE)),
    "times": (("same_category_visits", "checkins_count", "users_count", "photos_count"), 1.0),
    **dict.fromkeys(("visit", "visits"), (("same_category_visits", "history_window"), 1.0)),
    **dict.fromkeys(("check-in", "check-ins"), (("checkins_count",), 1.0)),
    # The only share the data has: visits of the stop's type over the history window.
    "%": (("visit_share",), 100.0),
    "": (("stop_count", "same_category_visits", "history_window", "in_range", "num_stops",
          "pool_size", "steps_since_category", "checkins_count", "users_count", "photos_count"),
         1.0),
}
_COUNT_UNITS = ("", "times", "visit", "visits", "check-in", "check-ins")


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

    numbers: list[tuple[str, float]] = []
    strings: set[str] = set()
    for ref in sentence.evidence_refs:
        try:
            value = resolve_ref(evidence, ref)
        except KeyError:
            return verdict("unsupported", f"cites a path that does not exist: {ref}")
        # Numbers come only from this stop's own fields (or route-level ones), cited as fields:
        # citing a whole record does not vouch for every number inside it.
        other_stop = step is not None and _stop_of(ref) not in (None, step - 1)
        whole = isinstance(value, dict) and any(isinstance(v, dict) for v in value.values())
        for key, leaf in _leaves(value, _last_key(ref)):
            if isinstance(leaf, str):
                strings.add(leaf.strip().casefold())
            elif (isinstance(leaf, (int, float)) and not isinstance(leaf, bool)
                  and not other_stop and not whole):
                numbers.append((key, float(leaf)))
    found = dict(numbers)
    if found.get("history_window") and "same_category_visits" in found:
        numbers.append(("visit_share", found["same_category_visits"] / found["history_window"]))
    # How many stops the route has is a fact of the evidence without a field ("three museums").
    numbers.append(("stop_count", float(len(evidence.get("steps") or []))))

    text = sentence.text
    named, rest = _named_categories(text, category_names)
    # Read with place-type names taken out: "Best Buy" is a type, "the best" is a claim.
    for pattern, claim in ((_ABSENT_ATTRIBUTES, "claims"), (_COMPARISON, "makes the comparison")):
        found = pattern.search(rest)
        if found:
            return verdict(
                "unsupported", f'{claim} "{found.group(0)}", which the data cannot show'
            )

    steps = evidence.get("steps") or []
    own = steps[step - 1] if step is not None and 0 < step <= len(steps) else None
    own_type = ((own or {}).get("poi") or {}).get("category_name") or ""
    route_types = _route_types(evidence)
    history = [(p.get("category_name") or "").strip().casefold()
               for p in evidence.get("history") or []]

    checked = False
    for name, negated, identity in named:
        key = name.casefold()
        if key not in strings and key not in route_types:
            return verdict(
                "unsupported", f"names {name}, which the cited evidence does not mention"
            )
        if own is not None and identity:
            if negated and key == own_type.strip().casefold():
                return verdict("unsupported", f"says this stop is not a {name}, but it is")
            if not negated and key != own_type.strip().casefold():
                return verdict(
                    "unsupported", f"says this stop is a {name}, but it is a {own_type.strip()}"
                )
        checked = True

    # How often the traveler went to a type; for the stop's own type, the visits its record counts.
    own_visits = ((own or {}).get("history") or {}).get("same_category_visits")

    def visits(name: str) -> int:
        if own_visits is not None and name.casefold() == own_type.strip().casefold():
            return own_visits
        return history.count(name.casefold())

    # "Often" and "new to you" are read with the types named in their own clause. Without one,
    # "new to you" is about this stop's type (or, in the summary, every stop's), and "often" is
    # about habit in general, which the evidence does not count.
    for pattern, holds, claim in ((_OFTEN, lambda c: c >= 2, "you often go there"),
                                  (_NEW, lambda c: c == 0, "it is new to you")):
        for found in pattern.finditer(text):
            clause = _clause(text, found.start(), found.end())
            if pattern is _NEW and _THIS_PLACE.search(clause):
                if own is not None:
                    if (own.get("history") or {}).get("visited_this_poi"):
                        return verdict("unsupported", "says you have not been here, but you have")
                    checked = True
                continue
            in_clause = [name for name, _, _ in named if _name_pattern(name).search(clause)]
            if in_clause:
                counts = [visits(name) for name in in_clause]
            elif pattern is _NEW and own_type:
                counts = [visits(own_type)]
            elif pattern is _NEW and own is None and steps:
                counts = [max((s.get("history") or {}).get("same_category_visits", 0)
                              for s in steps)]
            else:
                continue
            if not any(holds(c) for c in counts):
                return verdict(
                    "unsupported", f'says "{found.group(0)}", but the history does not show '
                    f"that {claim}"
                )
            checked = True

    # Counts of stops: all of them, those after the first, or those of a named type.
    route_types_on_stops = [((s.get("poi") or {}).get("category_name") or "").strip().casefold()
                            for s in steps]
    if len(steps) > 1:
        numbers.append(("stop_count", float(len(steps) - 1)))
    for name, _, _ in named:
        of_type = route_types_on_stops.count(name.casefold())
        if of_type:
            numbers.append(("stop_count", float(of_type)))

    rest = _STEP_LABEL.sub(" ", rest)
    claims = [(m.group(1), (m.group(2) or "").casefold()) for m in _NUMBER.finditer(rest)]
    claims += [(str(_NUMBER_WORDS[m.group(1).casefold()]), (m.group(2) or "").casefold())
               for m in _NUMBER_WORD.finditer(rest)]
    for token, unit in claims:
        if not _number_supported(token, unit, numbers):
            shown = f"{token} {unit}".strip()
            return verdict("unsupported", f"states {shown}, which no cited value supports")
        checked = True

    if not checked:
        return verdict("unverifiable", "states no number, place type or visit pattern to check")
    return verdict("supported")


def _leaves(value: Any, key: str) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for name, item in value.items():
            yield from _leaves(item, name)
    elif isinstance(value, list):
        for item in value:
            yield from _leaves(item, key)
    else:
        yield key, value


def _last_key(ref: str) -> str:
    return re.sub(r"\[\d+\]", "", ref.rsplit(".", 1)[-1])


def _stop_of(ref: str) -> int | None:
    match = re.match(r"steps\[(\d+)\]", ref)
    return int(match.group(1)) if match else None


def _route_types(evidence: dict[str, Any]) -> set[str]:
    """Place types on the route, in the history or in the request, which a sentence may name
    without citing them; what a stop is said to be is checked separately."""

    names = {p.get("category_name") for p in evidence.get("history") or []}
    names |= {(s.get("poi") or {}).get("category_name") for s in evidence.get("steps") or []}
    intent = evidence.get("intent") or {}
    names |= {m.get("category_name") for m in intent.get("want", []) + intent.get("avoid", [])}
    return {n.strip().casefold() for n in names if n and n.strip()}


def _number_supported(token: str, unit: str, cited: list[tuple[str, float]]) -> bool:
    value = float(token)
    if "." in token:
        tolerance = 0.5 * 10 ** -len(token.split(".")[1])
    elif unit in _COUNT_UNITS:
        tolerance = 0.0  # counts are exact
    else:
        zeros = len(token) - len(token.rstrip("0")) if token != "0" else 0
        tolerance = 0.5 * 10**zeros  # "100 m" may be rounded to the nearest 50
    tolerance += 1e-9

    # A bare integer states a count; a bare decimal is read against any cited value.
    keys, scale = _UNITS[unit] if unit != "" or "." not in token else (None, 1.0)
    for key, number in cited:
        if keys is not None and key not in keys:
            continue
        if abs(number * scale - value) <= tolerance:
            return True
    return False


@functools.lru_cache(maxsize=4096)
def _name_pattern(name: str) -> re.Pattern[str]:
    flags = re.IGNORECASE if " " in name else 0
    return re.compile(rf"(?<![\w]){re.escape(name)}(?:e?s)?(?![\w])", flags)


def _clause(text: str, start: int, end: int) -> str:
    """The part of the sentence around text[start:end] between clause breaks."""

    before = [m.end() for m in _CLAUSE_BREAK.finditer(text, 0, start)]
    after = _CLAUSE_BREAK.search(text, end)
    return text[(before[-1] if before else 0) : (after.start() if after else len(text))]


def _named_categories(
    text: str, category_names: list[str]
) -> tuple[list[tuple[str, bool, bool]], str]:
    """Place types the text names, longest first so "History Museum" is not also "Museum",
    each with whether it is negated and whether it is said to be the stop itself; and the
    text with those names removed. Multi-word names match in any case, one-word names only
    as spelled ("Target", not "target"), both with a plural s."""

    remaining = text
    found = []
    for name in category_names:
        pattern = _name_pattern(name)
        match = pattern.search(remaining)
        if match:
            before = remaining[: match.start()]
            found.append((name, bool(_NEGATION.search(before)), bool(_IDENTITY.search(before))))
            remaining = pattern.sub(" ", remaining)
    return found, remaining
