"""Ranking metrics for offline reranker evaluation."""

from __future__ import annotations

from typing import Any


def _is_hit(rank: int | None, k: int) -> float:
    return 1.0 if rank is not None and rank <= k else 0.0


def _reciprocal_rank(rank: int | None) -> float:
    return 0.0 if rank is None or rank <= 0 else 1.0 / float(rank)


def average_ground_truth_rank(samples: list[dict[str, Any]], field: str) -> dict[str, Any]:
    """Average rank over samples where the ground truth is present in top-k."""

    found_ranks = [
        int(sample[field])
        for sample in samples
        if sample.get(field) is not None
    ]
    return {
        "average_rank": (sum(found_ranks) / len(found_ranks)) if found_ranks else None,
        "found_count": len(found_ranks),
        "missing_count": len(samples) - len(found_ranks),
    }


def compute_ranking_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute core ranking metrics for baseline and semantic rerank outputs."""

    total = len(samples)
    if total == 0:
        empty_rank = {"average_rank": None, "found_count": 0, "missing_count": 0}
        return {
            "sample_count": 0,
            "before": {
                "hit@1": 0.0,
                "hit@5": 0.0,
                "mrr": 0.0,
                "average_ground_truth_rank": empty_rank["average_rank"],
                "ground_truth_rank_found_count": empty_rank["found_count"],
                "ground_truth_rank_missing_count": empty_rank["missing_count"],
            },
            "after": {
                "hit@1": 0.0,
                "hit@5": 0.0,
                "mrr": 0.0,
                "average_ground_truth_rank": empty_rank["average_rank"],
                "ground_truth_rank_found_count": empty_rank["found_count"],
                "ground_truth_rank_missing_count": empty_rank["missing_count"],
            },
        }

    before_rank_stats = average_ground_truth_rank(samples, "target_rank_before")
    after_rank_stats = average_ground_truth_rank(samples, "target_rank_after")

    before = {
        "hit@1": sum(_is_hit(sample.get("target_rank_before"), 1) for sample in samples) / total,
        "hit@5": sum(_is_hit(sample.get("target_rank_before"), 5) for sample in samples) / total,
        "mrr": sum(_reciprocal_rank(sample.get("target_rank_before")) for sample in samples) / total,
        "average_ground_truth_rank": before_rank_stats["average_rank"],
        "ground_truth_rank_found_count": before_rank_stats["found_count"],
        "ground_truth_rank_missing_count": before_rank_stats["missing_count"],
    }
    after = {
        "hit@1": sum(_is_hit(sample.get("target_rank_after"), 1) for sample in samples) / total,
        "hit@5": sum(_is_hit(sample.get("target_rank_after"), 5) for sample in samples) / total,
        "mrr": sum(_reciprocal_rank(sample.get("target_rank_after")) for sample in samples) / total,
        "average_ground_truth_rank": after_rank_stats["average_rank"],
        "ground_truth_rank_found_count": after_rank_stats["found_count"],
        "ground_truth_rank_missing_count": after_rank_stats["missing_count"],
    }
    return {
        "sample_count": total,
        "before": before,
        "after": after,
        "delta": {
            "hit@1": after["hit@1"] - before["hit@1"],
            "hit@5": after["hit@5"] - before["hit@5"],
            "mrr": after["mrr"] - before["mrr"],
            "average_ground_truth_rank": (
                None
                if before["average_ground_truth_rank"] is None or after["average_ground_truth_rank"] is None
                else after["average_ground_truth_rank"] - before["average_ground_truth_rank"]
            ),
        },
    }
