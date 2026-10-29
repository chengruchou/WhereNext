"""Turn a natural-language request into an Intent and derive the ranking weights.

Gemini parses the request into a ParsedIntent whose category hints must come
from the dataset's vocabulary. When Gemini is unavailable or returns invalid
output, a keyword parser takes over, so the demo keeps working offline. Either
way, the resolver keeps only categories that exist in the POI data.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Literal

from google import genai
from google.genai import types

from contracts.intent import (
    CategoryMatch,
    Intent,
    IntentPhrase,
    MatchMethod,
    ParsedIntent,
    ParserTrace,
    SteeringControls,
)
from services.model_config import RecommendationConfig


logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 500
MAX_MATCHES_PER_PHRASE = 8
DEFAULT_NUM_STOPS = 3
DEFAULT_TRAVEL_MODE = "drive"  # matches the route mode the map draws
WALKING_DISTANCE_KM = 1.0

_STOPWORDS = set(
    """
    a an the some something somewhere someplace place spot go get want like would nice good
    great to for of and or with in at on near nearby before after then maybe really very bit
    kind sort type i me my we our be is are it that this there here other else let can could
    should please visit see try find time
    """.split()
)
# Constraint words set budgets and modes. As category words they would match brand
# categories such as "Design Within Reach" or "24 Hour Fitness".
_STOPWORDS |= set(
    """
    within distance walk walking walkable drive driving car bus metro transit train hour minute
    mile stop open late early new usual different definitely must only need
    """.split()
)

_SYSTEM_PROMPT = """\
You turn a traveler's request into structured fields for a point-of-interest recommender.

Rules:
- Copy each wanted or avoided thing as a short phrase from the request, in the request's language.
- For each phrase, list the categories from CATEGORIES that fit it, spelled exactly as listed.
  Leave the list empty if none fit. Never invent a category.
- Put anything the system cannot check into "unsupported": opening hours, prices, ratings,
  reviews, crowds, weather, accessibility. The data has only categories, locations and visit counts.
- strength: "firm" if the user insists (must, definitely, only); "soft" if they hedge (maybe,
  something like); null if no kind of place is requested.
- explore: "new" if they want places unlike their usual ones; "familiar" if they want their
  usual kind of place; otherwise null.
- Leave a number null unless the request states it. "Walking distance" means max_hop_km 1.0
  and travel_mode "walk".

CATEGORIES:
"""


class CategoryVocabulary:
    """Category names exactly as they appear in the POI metadata."""

    def __init__(self, names: list[str]):
        self.names = sorted({name for name in names if name and name.strip()}, key=str.casefold)
        self._by_key = {_key(name): name for name in self.names}
        self._words = {name: _words(name) for name in self.names}

    @classmethod
    def from_metadata(cls, path: Path) -> CategoryVocabulary:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = payload.values() if isinstance(payload, dict) else payload
        return cls([row.get("category_name") or "" for row in rows])

    def exact(self, name: str) -> str | None:
        return self._by_key.get(_key(name))

    def lexical(self, phrase: str) -> list[str]:
        """Categories sharing a content word with the phrase; generic names first."""

        words = content_words(phrase)
        scored = []
        for name in self.names:
            hits = sum(
                1 for word in words if any(words_match(word, other) for other in self._words[name])
            )
            if hits:
                scored.append((-hits, len(name), name))
        return [name for _, _, name in sorted(scored)][:MAX_MATCHES_PER_PHRASE]


class IntentParser:
    def __init__(self, config: RecommendationConfig, client: Any | None = None):
        self.config = config
        self._client = client
        self._vocabulary: CategoryVocabulary | None = None
        self._lock = threading.Lock()

    def vocabulary(self) -> CategoryVocabulary:
        if self._vocabulary is None:
            with self._lock:
                if self._vocabulary is None:
                    self._vocabulary = CategoryVocabulary.from_metadata(
                        self.config.poi_metadata_path
                    )
        return self._vocabulary

    def parse(self, query: str) -> Intent:
        vocabulary = self.vocabulary()
        start = time.perf_counter()
        parsed = self._parse_with_llm(query, vocabulary)
        source: Literal["llm", "keyword"] = "llm"
        if parsed is None:
            parsed = parse_with_keywords(query, vocabulary)
            source = "keyword"
        trace = ParserTrace(
            model=self.config.intent_model if source == "llm" else "keyword",
            latency_ms=(time.perf_counter() - start) * 1000.0,
            fallback=source != "llm",
        )
        return resolve_intent(
            parsed, query=query, vocabulary=vocabulary, source=source, parser=trace
        )

    def _parse_with_llm(self, query: str, vocabulary: CategoryVocabulary) -> ParsedIntent | None:
        client = self._get_client()
        if client is None:
            logger.info("GEMINI_API_KEY is not set; using the keyword intent parser.")
            return None
        try:
            response = client.models.generate_content(
                model=self.config.intent_model,
                contents=f"Request: {query}",
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT + "\n".join(vocabulary.names),
                    response_mime_type="application/json",
                    response_json_schema=ParsedIntent.model_json_schema(),
                    temperature=0.0,
                    # Flash models only: skip thinking to keep parsing interactive.
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            return ParsedIntent.model_validate_json(response.text or "")
        except Exception as exc:
            logger.warning("LLM intent parsing failed; using the keyword parser: %s", exc)
            return None

    def _get_client(self) -> Any | None:
        if self._client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return None
            self._client = genai.Client(api_key=api_key)
        return self._client


def resolve_intent(
    parsed: ParsedIntent,
    *,
    query: str,
    vocabulary: CategoryVocabulary,
    source: Literal["llm", "keyword", "user_edit"],
    parser: ParserTrace | None = None,
) -> Intent:
    """Keep only dataset categories; an avoided category is never also wanted."""

    hint_method: MatchMethod = {
        "llm": "llm_hint",
        "keyword": "lexical",
        "user_edit": "user_edit",
    }[source]
    avoid, avoid_unresolved = _resolve_phrases(parsed.avoid, vocabulary, hint_method)
    want, want_unresolved = _resolve_phrases(parsed.want, vocabulary, hint_method)
    avoided = {match.category_name for match in avoid}
    return Intent(
        query=query,
        source=source,
        want=[match for match in want if match.category_name not in avoided],
        avoid=avoid,
        strength=parsed.strength or "soft",
        explore=parsed.explore or "balanced",
        num_stops=parsed.num_stops or DEFAULT_NUM_STOPS,
        time_budget_min=parsed.time_budget_min,
        max_hop_km=parsed.max_hop_km,
        travel_mode=parsed.travel_mode or DEFAULT_TRAVEL_MODE,
        unsupported=parsed.unsupported,
        unresolved=want_unresolved + avoid_unresolved,
        parser=parser,
    )


def controls_for(intent: Intent | None, config: RecommendationConfig) -> SteeringControls:
    """Fixed policy from the intent's wording to the ranking weights."""

    if intent is None:
        return SteeringControls()
    habit_intent = 0.0
    if intent.want:
        firm = intent.strength == "firm"
        habit_intent = config.intent_lambda_firm if firm else config.intent_lambda_soft
    explore = {
        "familiar": 0.0,
        "balanced": config.explore_balanced,
        "new": config.explore_new,
    }[intent.explore]
    return SteeringControls(habit_intent=habit_intent, explore=explore, source="intent")


def parse_with_keywords(query: str, vocabulary: CategoryVocabulary) -> ParsedIntent:
    """Offline fallback for English requests: category words, negations, numbers."""

    text = query.casefold()
    want: list[IntentPhrase] = []
    avoid: list[IntentPhrase] = []
    for clause in re.split(r"[,.;!?]+|\band\b|\bthen\b", text):
        clause = clause.strip()
        if not clause:
            continue
        negation = r"\b(?:no|not|nothing|avoid|without|except|skip)\s+([^,.;!?]+)"
        for match in re.finditer(negation, clause):
            phrase = " ".join(match.group(1).split()[:4])
            clause = clause.replace(match.group(0), " ")
            hints = vocabulary.lexical(phrase)
            if hints:  # "not been there" is not a category to avoid
                avoid.append(IntentPhrase(phrase=phrase, category_hints=hints))
        hints = vocabulary.lexical(clause)
        if hints:
            want.append(IntentPhrase(phrase=" ".join(clause.split()), category_hints=hints))

    travel_mode = None
    max_hop_km = None
    if re.search(r"\bwalk(?:ing|able)?\b", text):
        travel_mode = "walk"
        if "walking distance" in text:
            max_hop_km = WALKING_DISTANCE_KM
    elif re.search(r"\b(?:drive|driving|car)\b", text):
        travel_mode = "drive"
    elif re.search(r"\b(?:transit|bus|metro|by train)\b", text):
        travel_mode = "transit"
    distance = re.search(r"\bwithin\s+(\d+(?:\.\d+)?)\s*(km|kilomet\w*|miles?|mi)\b", text)
    if distance:
        max_hop_km = float(distance.group(1)) * (1.609 if distance.group(2).startswith("mi") else 1)

    return ParsedIntent(
        want=want,
        avoid=avoid,
        strength=_strength(text) if want else None,
        num_stops=_num_stops(text),
        time_budget_min=_time_budget_min(text),
        max_hop_km=min(max_hop_km, 50.0) if max_hop_km else None,
        travel_mode=travel_mode,
        explore=_explore(text),
        unsupported=_unsupported(text),
    )


def _resolve_phrases(
    phrases: list[IntentPhrase],
    vocabulary: CategoryVocabulary,
    hint_method: MatchMethod,
) -> tuple[list[CategoryMatch], list[str]]:
    matches: list[CategoryMatch] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        resolved = [(name, hint_method) for name in map(vocabulary.exact, phrase.category_hints)]
        resolved = [(name, method) for name, method in resolved if name is not None]
        if not resolved:
            resolved = [(name, "lexical") for name in vocabulary.lexical(phrase.phrase)]
        if not resolved:
            unresolved.append(phrase.phrase)
            continue
        for name, method in resolved:
            if name not in seen:
                seen.add(name)
                matches.append(
                    CategoryMatch(category_name=name, phrase=phrase.phrase, method=method)
                )
    return matches, unresolved


def _strength(text: str) -> Literal["soft", "firm"]:
    firm = r"\b(?:must|definitely|need to|have to|has to|only|really want)\b"
    return "firm" if re.search(firm, text) else "soft"


def _explore(text: str) -> Literal["familiar", "balanced", "new"] | None:
    if re.search(r"\b(?:new|never been|haven't been|not been|different|unusual|explore)\b", text):
        return "new"
    if re.search(r"\b(?:usual|favou?rite|same as|regular|like always)\b", text):
        return "familiar"
    return None


_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _num_stops(text: str) -> int | None:
    match = re.search(r"\b(\d+|one|two|three|four|five)\s+(?:stops?|places?|spots?)\b", text)
    if not match:
        return None
    value = _NUMBER_WORDS.get(match.group(1)) or int(match.group(1))
    return min(max(value, 1), 5)


def _time_budget_min(text: str) -> int | None:
    hours = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", text)
    minutes = re.search(r"\b(\d+)\s*(?:minutes?|mins?)\b", text)
    if hours:
        value = float(hours.group(1)) * 60
    elif minutes:
        value = float(minutes.group(1))
    else:
        return None
    return int(min(max(value, 10), 720))


def _unsupported(text: str) -> list[str]:
    found = [match.group(0) for match in re.finditer(r"\bopen(?:\s+(?:late|now|early))?\b", text)]
    found += re.findall(
        r"\b(?:cheap|expensive|price[sd]?|rating|rated|reviews?|crowded|quiet|weather)\b", text
    )
    return list(dict.fromkeys(found))


def _key(name: str) -> str:
    return " ".join(name.casefold().split())


def _words(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9']+", text.casefold())
    return [word[:-1] if len(word) > 3 and word.endswith("s") else word for word in words]


def content_words(text: str) -> list[str]:
    """Normalized words of the text, without stopwords, numbers and very short words."""

    return [
        word
        for word in _words(text)
        if word not in _STOPWORDS and len(word) >= 3 and not word.isdigit()
    ]


def words_match(word: str, other: str) -> bool:
    """Same word, or the same first five letters ("cultural" and "culture")."""

    return word == other or (len(word) >= 5 and len(other) >= 5 and word[:5] == other[:5])


_parser: IntentParser | None = None


def get_intent_parser() -> IntentParser:
    global _parser
    if _parser is None:
        _parser = IntentParser(RecommendationConfig.from_env())
    return _parser
