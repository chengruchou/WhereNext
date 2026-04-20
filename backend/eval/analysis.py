"""Analysis helpers for offline reranker evaluation."""

from __future__ import annotations

from typing import Any


def seen_item_ratio(predictions: list[dict[str, Any]], history_item_ids: list[int]) -> float:
    """Compute the fraction of top-k predictions already present in history."""

    if not predictions:
        return 0.0
    seen = set(int(item_id) for item_id in history_item_ids)
    hits = sum(1 for pred in predictions if int(pred.get("item_id", -1)) in seen)
    return hits / len(predictions)


def top1_is_seen(predictions: list[dict[str, Any]], history_item_ids: list[int]) -> bool:
    """Return whether the top-1 predicted item already appears in the history prefix."""

    if not predictions:
        return False
    top_item_id = predictions[0].get("item_id")
    return top_item_id is not None and int(top_item_id) in set(int(x) for x in history_item_ids)


def improved_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return samples where reranking improved the ground-truth rank."""

    return [
        sample
        for sample in samples
        if sample.get("target_rank_before") is not None
        and sample.get("target_rank_after") is not None
        and int(sample["target_rank_after"]) < int(sample["target_rank_before"])
    ]


def worsened_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return samples where reranking worsened the ground-truth rank."""

    return [
        sample
        for sample in samples
        if sample.get("target_rank_before") is not None
        and sample.get("target_rank_after") is not None
        and int(sample["target_rank_after"]) > int(sample["target_rank_before"])
    ]


def summarize_analysis(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate additional diagnostics over per-sample results."""

    total = len(samples)
    if total == 0:
        return {
            "average_seen_item_ratio_before": 0.0,
            "average_seen_item_ratio_after": 0.0,
            "top1_seen_rate_before": 0.0,
            "top1_seen_rate_after": 0.0,
            "improved_count": 0,
            "worsened_count": 0,
            "unchanged_count": 0,
            "improved_sample_ids": [],
            "worsened_sample_ids": [],
        }

    improved = improved_samples(samples)
    worsened = worsened_samples(samples)
    return {
        "average_seen_item_ratio_before": (
            sum(float(sample.get("seen_item_ratio_before", 0.0)) for sample in samples) / total
        ),
        "average_seen_item_ratio_after": (
            sum(float(sample.get("seen_item_ratio_after", 0.0)) for sample in samples) / total
        ),
        "top1_seen_rate_before": (
            sum(1 for sample in samples if bool(sample.get("top1_seen_before"))) / total
        ),
        "top1_seen_rate_after": (
            sum(1 for sample in samples if bool(sample.get("top1_seen_after"))) / total
        ),
        "improved_count": len(improved),
        "worsened_count": len(worsened),
        "unchanged_count": total - len(improved) - len(worsened),
        "improved_sample_ids": [int(sample["sample_id"]) for sample in improved],
        "worsened_sample_ids": [int(sample["sample_id"]) for sample in worsened],
    }
