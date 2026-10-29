"""Graded intent relevance: how well each POI category answers the wanted phrases.

Gowalla POIs carry no names, so a POI's category is its only text. For each
wanted phrase, the categories the parser resolved it to score in [0.5, 1],
ordered by the cosine similarity between the user's own words and the category
name; every other category scores in [0, 0.5], scaled against the best resolved
one, so related categories get partial credit. A category takes its best score
over the phrases. The parser's resolution keeps phrases the encoder handles
poorly ("dinner", non-English text) on the right categories.

Without sentence-transformers the scorer falls back to word coverage: resolved
categories score 1, others half the share of the phrase's content words that
the category name contains. The scorer's `method` says which one ran.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np

from contracts.intent import Intent
from services.intent_parser import content_words, words_match


logger = logging.getLogger(__name__)

LEXICAL = "lexical"
RESOLVED_FLOOR = 0.5  # resolved categories score in [0.5, 1], all others in [0, 0.5]

# category name -> (value in [0, 1], raw cosine similarity or None)
IntentScores = dict[str, tuple[float, float | None]]


class IntentScorer:
    def __init__(self, model_name: str, categories: list[str]):
        self.model_name = model_name
        self.categories = sorted(set(categories))
        self._model: Any = None
        self._category_vectors: np.ndarray | None = None
        self._lock = threading.Lock()
        self._load_failed = model_name == LEXICAL

    @property
    def method(self) -> str:
        if self._load_failed:
            return LEXICAL
        return f"embedding ({self.model_name})"

    def score(self, intent: Intent | None) -> IntentScores:
        phrases = _resolved_by_phrase(intent)
        if not phrases:
            return {}
        if self._ensure_model():
            return self._embedding_scores(phrases)
        return self._lexical_scores(phrases)

    def _ensure_model(self) -> bool:
        if self._load_failed:
            return False
        if self._model is not None:
            return True
        with self._lock:
            if self._model is None and not self._load_failed:
                try:
                    from sentence_transformers import SentenceTransformer

                    model = SentenceTransformer(self.model_name, device="cpu")
                    self._category_vectors = model.encode(
                        self.categories, normalize_embeddings=True, convert_to_numpy=True
                    )
                    self._model = model
                except Exception as exc:
                    logger.warning("Intent encoder unavailable; using word coverage: %s", exc)
                    self._load_failed = True
        return self._model is not None

    def _embedding_scores(self, phrases: dict[str, set[str]]) -> IntentScores:
        queries = self._model.encode(
            list(phrases), normalize_embeddings=True, convert_to_numpy=True
        )
        index = {name: i for i, name in enumerate(self.categories)}
        scores: IntentScores = {}
        all_similarities = queries @ self._category_vectors.T
        for resolved, similarities in zip(phrases.values(), all_similarities, strict=True):
            sims = similarities.astype(float)
            inside = [sims[index[name]] for name in resolved if name in index]
            if not inside:
                continue
            low, best, lowest = min(inside), max(inside), float(sims.min())
            for name, raw in zip(self.categories, sims, strict=True):
                if name in resolved:
                    rel = (raw - low) / (best - low) if best - low > 1e-9 else 1.0
                    value = RESOLVED_FLOOR + (1.0 - RESOLVED_FLOOR) * rel
                else:
                    rel = (raw - lowest) / (best - lowest) if best - lowest > 1e-9 else 0.0
                    value = RESOLVED_FLOOR * min(max(rel, 0.0), 1.0)
                if name not in scores or value > scores[name][0]:
                    scores[name] = (float(value), float(raw))
        return scores

    def _lexical_scores(self, phrases: dict[str, set[str]]) -> IntentScores:
        scores: IntentScores = {}
        for phrase, resolved in phrases.items():
            words = content_words(phrase)
            for name in self.categories:
                if name in resolved:
                    value = 1.0
                elif words:
                    category_words = content_words(name)
                    covered = sum(any(words_match(w, c) for c in category_words) for w in words)
                    value = RESOLVED_FLOOR * covered / len(words)
                else:
                    value = 0.0
                if name not in scores or value > scores[name][0]:
                    scores[name] = (value, None)
        return scores


def _resolved_by_phrase(intent: Intent | None) -> dict[str, set[str]]:
    """Wanted phrase -> the dataset categories it resolved to."""

    if intent is None:
        return {}
    resolved: dict[str, set[str]] = {}
    for match in intent.want:
        resolved.setdefault(match.phrase, set()).add(match.category_name)
    return resolved
