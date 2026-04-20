"""Lightweight multi-view semantic fusion.

This module adapts the spirit of POI-Enhancer semantic fusion at inference time.
It intentionally does not implement the paper's training-time Dual Feature
Alignment, Cross Attention Fusion, or contrastive objectives. Instead, it fuses
the three prompt-view embeddings with deterministic weights so the pipeline
remains lightweight and deployable in this repository.
"""

from __future__ import annotations

import numpy as np


class WeightedSemanticFusion:
    """Deterministic weighted fusion of visit, location, and category views."""

    def __init__(self, view_weights: dict[str, float]):
        self.view_weights = view_weights

    def fuse(self, visit_embedding: np.ndarray, location_embedding: np.ndarray, category_embedding: np.ndarray) -> np.ndarray:
        """Fuse three view embeddings into one POI semantic vector."""

        weights = self._normalized_weights()
        fused = (
            weights["visit_pattern"] * visit_embedding
            + weights["location"] * location_embedding
            + weights["category"] * category_embedding
        )
        norm = np.linalg.norm(fused)
        return fused if norm == 0 else fused / norm

    def _normalized_weights(self) -> dict[str, float]:
        total = sum(max(float(v), 0.0) for v in self.view_weights.values())
        if total <= 0:
            return {"visit_pattern": 1 / 3, "location": 1 / 3, "category": 1 / 3}
        return {
            "visit_pattern": max(float(self.view_weights.get("visit_pattern", 0.0)), 0.0) / total,
            "location": max(float(self.view_weights.get("location", 0.0)), 0.0) / total,
            "category": max(float(self.view_weights.get("category", 0.0)), 0.0) / total,
        }

