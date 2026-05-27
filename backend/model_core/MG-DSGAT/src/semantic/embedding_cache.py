"""Persistence and validation helpers for POI semantic embeddings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class SemanticEmbeddingStore:
    embeddings: np.ndarray
    item_id_to_index: dict[int, int]
    raw_location_id_to_index: dict[int, int]
    rows: list[dict[str, Any]]
    manifest: dict[str, Any]
    view_embeddings: dict[str, np.ndarray] | None = None
    view_names: list[str] | None = None
    default_view: str | None = None

    def get_by_item_id(self, item_id: int, view: str | None = None) -> np.ndarray:
        return self._matrix_for_view(view)[self.item_id_to_index[int(item_id)]]

    def get_by_raw_location_id(self, raw_location_id: int, view: str | None = None) -> np.ndarray:
        return self._matrix_for_view(view)[self.raw_location_id_to_index[int(raw_location_id)]]

    def has_item_id(self, item_id: int, view: str | None = None) -> bool:
        return int(item_id) in self.item_id_to_index and self.has_view(view)

    def has_raw_location_id(self, raw_location_id: int, view: str | None = None) -> bool:
        return int(raw_location_id) in self.raw_location_id_to_index and self.has_view(view)

    def has_view(self, view: str | None = None) -> bool:
        if self.view_embeddings is None:
            return view is None or str(view) == str(self.default_view or self.manifest.get("view"))
        return self._normalize_view(view) in self.view_embeddings

    def validate_norms(self, tolerance: float = 1e-3) -> dict[str, Any]:
        if self.view_embeddings is None:
            return summarize_embedding_norms(self.embeddings, tolerance=tolerance)
        return {
            view: summarize_embedding_norms(matrix, tolerance=tolerance)
            for view, matrix in self.view_embeddings.items()
        }

    def validate_unique_ids(self) -> dict[str, Any]:
        return summarize_unique_ids(self.rows)

    def validate_coverage(
        self,
        item_ids: list[int] | None = None,
        raw_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        item_ids = item_ids or []
        raw_ids = raw_ids or []
        missing_item_ids = [
            int(item_id) for item_id in item_ids if int(item_id) not in self.item_id_to_index
        ]
        missing_raw_ids = [
            int(raw_id) for raw_id in raw_ids if int(raw_id) not in self.raw_location_id_to_index
        ]
        return {
            "item_ids_checked": len(item_ids),
            "raw_ids_checked": len(raw_ids),
            "missing_item_id_count": len(missing_item_ids),
            "missing_raw_location_id_count": len(missing_raw_ids),
            "missing_item_id_examples": missing_item_ids[:10],
            "missing_raw_location_id_examples": missing_raw_ids[:10],
        }

    def _matrix_for_view(self, view: str | None = None) -> np.ndarray:
        if self.view_embeddings is None:
            if not self.has_view(view):
                raise KeyError(f"Embedding view not found: {view}")
            return self.embeddings
        normalized_view = self._normalize_view(view)
        try:
            return self.view_embeddings[normalized_view]
        except KeyError as exc:
            raise KeyError(f"Embedding view not found: {normalized_view}") from exc

    def _normalize_view(self, view: str | None = None) -> str:
        if view is not None:
            return str(view)
        if self.default_view is not None:
            return str(self.default_view)
        if self.view_names:
            if "all" in self.view_names:
                return "all"
            return str(self.view_names[0])
        return str(self.manifest.get("view", "all"))


def save_embedding_store(
    output_path,
    manifest_path,
    embeddings,
    rows,
    prompt_cache_path,
    prompt_manifest_path,
    encoder_config,
) -> dict[str, Any]:
    """Save embeddings and a JSON manifest, returning the manifest."""

    output_path = Path(output_path)
    manifest_path = Path(manifest_path)
    prompt_cache_path = Path(prompt_cache_path)
    prompt_manifest_path = Path(prompt_manifest_path)
    embeddings_np = np.asarray(embeddings, dtype=np.float32)
    rows = [_compact_row(row, index) for index, row in enumerate(rows)]

    if embeddings_np.ndim != 2:
        raise ValueError(f"embeddings must be rank-2, got shape {embeddings_np.shape}")
    if embeddings_np.shape[0] != len(rows):
        raise ValueError(
            f"Embedding row count {embeddings_np.shape[0]} does not match row metadata count {len(rows)}"
        )

    item_id_to_index, raw_location_id_to_index = build_id_mappings(rows)
    unique_summary = summarize_unique_ids(rows)
    norm_summary = summarize_embedding_norms(embeddings_np)
    prompt_manifest = _read_json_if_exists(prompt_manifest_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".pt":
        try:
            import torch
        except ImportError as exc:
            raise ImportError("Saving .pt embeddings requires torch to be installed.") from exc
        torch.save(torch.as_tensor(embeddings_np, dtype=torch.float32), output_path)
    elif output_path.suffix.lower() == ".npy":
        np.save(output_path, embeddings_np)
    else:
        raise ValueError("embedding output path must end with .pt or .npy")

    manifest = {
        "dataset": encoder_config.get("dataset", prompt_manifest.get("dataset", "Gowalla")),
        "prompt_cache_path": str(prompt_cache_path),
        "prompt_manifest_path": str(prompt_manifest_path),
        "prompt_cache_sha256": compute_file_sha256(prompt_cache_path),
        "prompt_manifest_sha256": compute_file_sha256(prompt_manifest_path),
        "embedding_output_path": str(output_path),
        "encoder_name": encoder_config.get("encoder_name"),
        "encoder_model_name": encoder_config.get("encoder_model_name"),
        "embedding_dim": int(embeddings_np.shape[1]),
        "pooling_method": encoder_config.get("pooling_method"),
        "prompt_prefix_mode": encoder_config.get("prompt_prefix_mode", "none"),
        "view_mode": encoder_config.get("view_mode", "single_view"),
        "normalize_embeddings": bool(encoder_config.get("normalize_embeddings", True)),
        "row_count": int(embeddings_np.shape[0]),
        "item_id_to_index": {str(key): int(value) for key, value in item_id_to_index.items()},
        "raw_location_id_to_index": {
            str(key): int(value) for key, value in raw_location_id_to_index.items()
        },
        "prompt_version": encoder_config.get("prompt_version") or prompt_manifest.get("prompt_version"),
        "view": encoder_config.get("view") or prompt_manifest.get("view"),
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "embedding_norm_summary": norm_summary,
        "missing_or_duplicate_id_summary": unique_summary,
        "rows": rows,
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def save_multiview_embedding_store(
    output_path,
    manifest_path,
    embeddings_by_view: dict[str, Any],
    rows,
    prompt_cache_path,
    prompt_manifest_path,
    encoder_config,
) -> dict[str, Any]:
    """Save one aligned embedding matrix per semantic view."""

    output_path = Path(output_path)
    manifest_path = Path(manifest_path)
    prompt_cache_path = Path(prompt_cache_path)
    prompt_manifest_path = Path(prompt_manifest_path)

    if not embeddings_by_view:
        raise ValueError("embeddings_by_view must not be empty")

    rows = [_compact_row(row, index) for index, row in enumerate(rows)]
    matrices: dict[str, np.ndarray] = {
        str(view): np.asarray(matrix, dtype=np.float32)
        for view, matrix in embeddings_by_view.items()
    }
    row_count = len(rows)
    embedding_dims: dict[str, int] = {}
    norm_summary: dict[str, Any] = {}
    for view, matrix in matrices.items():
        if matrix.ndim != 2:
            raise ValueError(f"Embedding view {view} must be rank-2, got shape {matrix.shape}")
        if matrix.shape[0] != row_count:
            raise ValueError(
                f"Embedding row count for view {view} ({matrix.shape[0]}) "
                f"does not match row metadata count {row_count}"
            )
        embedding_dims[view] = int(matrix.shape[1])
        norm_summary[view] = summarize_embedding_norms(matrix)

    item_id_to_index, raw_location_id_to_index = build_id_mappings(rows)
    unique_summary = summarize_unique_ids(rows)
    prompt_manifest = _read_json_if_exists(prompt_manifest_path)
    view_names = list(matrices.keys())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".pt":
        try:
            import torch
        except ImportError as exc:
            raise ImportError("Saving .pt embeddings requires torch to be installed.") from exc
        torch.save(
            {
                "format": "semantic_multiview_embedding_store_v1",
                "view_names": view_names,
                "embeddings_by_view": {
                    view: torch.as_tensor(matrix, dtype=torch.float32)
                    for view, matrix in matrices.items()
                },
            },
            output_path,
        )
    elif output_path.suffix.lower() == ".npz":
        np.savez(output_path, **{f"view__{view}": matrix for view, matrix in matrices.items()})
    else:
        raise ValueError("multi-view embedding output path must end with .pt or .npz")

    manifest = {
        "dataset": encoder_config.get("dataset", prompt_manifest.get("dataset", "Gowalla")),
        "format": "semantic_multiview_embedding_store_v1",
        "prompt_cache_path": str(prompt_cache_path),
        "prompt_manifest_path": str(prompt_manifest_path),
        "prompt_cache_sha256": compute_file_sha256(prompt_cache_path),
        "prompt_manifest_sha256": compute_file_sha256(prompt_manifest_path),
        "embedding_output_path": str(output_path),
        "encoder_name": encoder_config.get("encoder_name"),
        "encoder_model_name": encoder_config.get("encoder_model_name"),
        "view_names": view_names,
        "embedding_dims": embedding_dims,
        "embedding_dim": embedding_dims.get("all"),
        "pooling_method": encoder_config.get("pooling_method"),
        "prompt_prefix_mode": encoder_config.get("prompt_prefix_mode", "none"),
        "view_mode": encoder_config.get("view_mode", "multi_view"),
        "normalize_embeddings": bool(encoder_config.get("normalize_embeddings", True)),
        "row_count": int(row_count),
        "item_id_to_index": {str(key): int(value) for key, value in item_id_to_index.items()},
        "raw_location_id_to_index": {
            str(key): int(value) for key, value in raw_location_id_to_index.items()
        },
        "prompt_version": encoder_config.get("prompt_version") or prompt_manifest.get("prompt_version"),
        "view": "multi_view",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "embedding_norm_summary": norm_summary,
        "missing_or_duplicate_id_summary": unique_summary,
        "rows": rows,
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def load_embedding_store(output_path, manifest_path) -> SemanticEmbeddingStore:
    """Load an embedding matrix and manifest."""

    output_path = Path(output_path)
    manifest_path = Path(manifest_path)
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    view_embeddings = None
    view_names = None
    default_view = manifest.get("view")

    if output_path.suffix.lower() == ".pt":
        try:
            import torch
        except ImportError as exc:
            raise ImportError("Loading .pt embeddings requires torch to be installed.") from exc
        loaded = torch.load(output_path, map_location="cpu")
        if isinstance(loaded, dict) and "embeddings_by_view" in loaded:
            view_embeddings = {}
            for view, matrix in loaded["embeddings_by_view"].items():
                if hasattr(matrix, "detach"):
                    view_embeddings[str(view)] = matrix.detach().cpu().numpy()
                else:
                    view_embeddings[str(view)] = np.asarray(matrix)
            view_names = [str(view) for view in loaded.get("view_names", view_embeddings.keys())]
            default_view = "all" if "all" in view_embeddings else (view_names[0] if view_names else None)
            embeddings = view_embeddings[default_view] if default_view is not None else np.empty((0, 0))
        elif hasattr(loaded, "detach"):
            embeddings = loaded.detach().cpu().numpy()
        else:
            embeddings = np.asarray(loaded)
    elif output_path.suffix.lower() == ".npy":
        embeddings = np.load(output_path)
    elif output_path.suffix.lower() == ".npz":
        loaded_npz = np.load(output_path)
        view_embeddings = {
            key.removeprefix("view__"): np.asarray(loaded_npz[key])
            for key in loaded_npz.files
            if key.startswith("view__")
        }
        view_names = list(manifest.get("view_names", view_embeddings.keys()))
        default_view = "all" if "all" in view_embeddings else (view_names[0] if view_names else None)
        embeddings = view_embeddings[default_view] if default_view is not None else np.empty((0, 0))
    else:
        raise ValueError("embedding output path must end with .pt, .npy, or .npz")

    rows = manifest.get("rows", [])
    item_id_to_index = {
        int(key): int(value) for key, value in manifest.get("item_id_to_index", {}).items()
    }
    raw_location_id_to_index = {
        int(key): int(value)
        for key, value in manifest.get("raw_location_id_to_index", {}).items()
    }
    return SemanticEmbeddingStore(
        embeddings=np.asarray(embeddings, dtype=np.float32),
        item_id_to_index=item_id_to_index,
        raw_location_id_to_index=raw_location_id_to_index,
        rows=rows,
        manifest=manifest,
        view_embeddings=(
            {view: np.asarray(matrix, dtype=np.float32) for view, matrix in view_embeddings.items()}
            if view_embeddings is not None
            else None
        ),
        view_names=view_names or manifest.get("view_names"),
        default_view=default_view,
    )


def compute_file_sha256(path) -> str:
    path = Path(path)
    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def build_id_mappings(rows: list[dict[str, Any]]) -> tuple[dict[int, int], dict[int, int]]:
    item_id_to_index: dict[int, int] = {}
    raw_location_id_to_index: dict[int, int] = {}
    for index, row in enumerate(rows):
        item_id = row.get("item_id")
        raw_location_id = row.get("raw_location_id")
        if item_id is not None:
            item_id_to_index[int(item_id)] = index
        if raw_location_id is not None:
            raw_location_id_to_index[int(raw_location_id)] = index
    return item_id_to_index, raw_location_id_to_index


def summarize_embedding_norms(embeddings, tolerance: float = 1e-3) -> dict[str, Any]:
    embeddings = np.asarray(embeddings, dtype=np.float32)
    if embeddings.size == 0 or embeddings.shape[0] == 0:
        return {
            "count": 0,
            "min": None,
            "mean": None,
            "max": None,
            "non_unit_count": 0,
            "zero_norm_count": 0,
            "tolerance": float(tolerance),
        }
    norms = np.linalg.norm(embeddings, axis=1)
    return {
        "count": int(norms.shape[0]),
        "min": float(np.min(norms)),
        "mean": float(np.mean(norms)),
        "max": float(np.max(norms)),
        "non_unit_count": int(np.sum(np.abs(norms - 1.0) > float(tolerance))),
        "zero_norm_count": int(np.sum(norms == 0.0)),
        "tolerance": float(tolerance),
    }


def summarize_unique_ids(rows: list[dict[str, Any]]) -> dict[str, Any]:
    item_ids = [row.get("item_id") for row in rows]
    raw_ids = [row.get("raw_location_id") for row in rows]
    return {
        "row_count": len(rows),
        "missing_item_id_count": sum(1 for value in item_ids if value is None),
        "missing_raw_location_id_count": sum(1 for value in raw_ids if value is None),
        "unique_item_ids": len(set(value for value in item_ids if value is not None)),
        "unique_raw_location_ids": len(set(value for value in raw_ids if value is not None)),
        "duplicate_item_id_count": _duplicate_count(item_ids),
        "duplicate_raw_location_id_count": _duplicate_count(raw_ids),
    }


def _compact_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    compact = {
        "index": int(index),
        "item_id": _int_or_none(row.get("item_id")),
        "raw_location_id": _int_or_none(row.get("raw_location_id")),
        "view": row.get("view"),
        "prompt_version": row.get("prompt_version"),
        "metadata_hash": row.get("metadata_hash"),
    }
    if row.get("prompt_hash") is not None:
        compact["prompt_hash"] = row.get("prompt_hash")
    if row.get("prompt_hashes") is not None:
        compact["prompt_hashes"] = row.get("prompt_hashes")
    if row.get("metadata_summary") is not None:
        compact["metadata_summary"] = row.get("metadata_summary")
    return compact


def _duplicate_count(values: list[Any]) -> int:
    seen = set()
    duplicates = set()
    for value in values:
        if value is None:
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return len(duplicates)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, dict) else {}
