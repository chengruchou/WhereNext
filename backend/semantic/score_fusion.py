"""Score normalization and fusion helpers for future LLM reranking."""

from __future__ import annotations


def min_max_normalize(scores: list[float]) -> list[float]:
    """Normalize scores into [0, 1] with a stable equal-values fallback."""

    if not scores:
        return []

    values = [float(score) for score in scores]
    min_score = min(values)
    max_score = max(values)
    if max_score - min_score < 1e-12:
        return [1.0 for _ in values]

    return [(score - min_score) / (max_score - min_score) for score in values]


def rank_to_score(rank: int, n: int) -> float:
    """Convert a 1-based rank into a [0, 1] score."""

    if n <= 1:
        return 1.0
    clipped_rank = min(max(int(rank), 1), int(n))
    return (n - clipped_rank) / (n - 1)


def fuse_scores(normalized_sbr: float, llm_rank_score: float, alpha: float) -> float:
    """Fuse normalized SBR score with LLM rank score."""

    clipped_alpha = min(max(float(alpha), 0.0), 1.0)
    return clipped_alpha * float(normalized_sbr) + (1.0 - clipped_alpha) * float(llm_rank_score)
