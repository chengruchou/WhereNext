from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import sys
import threading
from argparse import Namespace
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

from services.model_config import RecommendationConfig


logger = logging.getLogger(__name__)


def _module_is_from_path(module: ModuleType | None, root: Path) -> bool:
    if module is None:
        return False
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    try:
        return Path(module_file).resolve().is_relative_to(root.resolve())
    except OSError:
        return False


def _evict_external_module(module_root: str, src_path: Path) -> None:
    for name in list(sys.modules):
        if name != module_root and not name.startswith(f"{module_root}."):
            continue
        if not _module_is_from_path(sys.modules.get(name), src_path):
            sys.modules.pop(name, None)


def _import_from_model_src(src_path: Path, module_name: str) -> ModuleType:
    src_text = str(src_path)
    if src_text not in sys.path:
        sys.path.insert(0, src_text)

    _evict_external_module(module_name.split(".")[0], src_path)
    module = importlib.import_module(module_name)
    if not _module_is_from_path(module, src_path):
        raise ImportError(f"Imported {module_name} from unexpected path: {module.__file__}")
    return module


def _load_module_from_file(alias: str, path: Path) -> ModuleType:
    existing = sys.modules.get(alias)
    if _module_is_from_path(existing, path.parent):
        return existing

    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _candidate_raw_id(row: dict[str, Any]) -> int | None:
    return _as_int(row.get("raw_poi_id", row.get("raw_location_id")))


def _candidate_item_id(row: dict[str, Any]) -> int | None:
    return _as_int(row.get("item_id"))


def _normalize_prediction_rows(
    rows: list[dict[str, Any]],
    raw2item: dict[int, int],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        raw_id = _candidate_raw_id(row)
        item_id = _candidate_item_id(row)
        if item_id is None and raw_id is not None:
            item_id = raw2item.get(raw_id)
        if raw_id is None or item_id is None:
            continue

        sbr_score = row.get("sbr_score")
        if sbr_score is None and row.get("candidate_source") != "spatial":
            sbr_score = row.get("score")
        spatial_score = row.get("spatial_score")
        semantic_score = row.get("semantic_score")
        final_score = row.get("final_score", row.get("semantic_fusion_score"))
        if final_score is None:
            final_score = row.get("spatial_fusion_score", row.get("score", 0.0))
        score = row.get("score")
        if score is None:
            score = sbr_score if sbr_score is not None else final_score

        normalized_row = dict(row)
        normalized_row.update(
            {
                "rank": rank,
                "raw_poi_id": int(raw_id),
                "raw_location_id": int(raw_id),
                "item_id": int(item_id),
                "score": float(score or 0.0),
                "sbr_score": None if sbr_score is None else float(sbr_score),
                "spatial_score": None
                if spatial_score is None
                else float(spatial_score),
                "semantic_score": None
                if semantic_score is None
                else float(semantic_score),
                "final_score": None if final_score is None else float(final_score),
            }
        )
        normalized.append(normalized_row)
    return normalized


class LatestSBRModel:
    def __init__(self, config: RecommendationConfig):
        self.config = config
        self._lock = threading.RLock()
        self._loaded = False
        self._infer_sbr: ModuleType | None = None
        self._torch = None
        self._model = None
        self._opt = None
        self._device = None
        self.raw2item: dict[int, int] = {}
        self.item2raw: dict[int, int] = {}

    def predict(self, raw_poi_ids: list[int], top_k: int | None = None) -> list[dict[str, Any]]:
        self._ensure_loaded()
        assert self._infer_sbr is not None
        assert self._model is not None
        assert self._opt is not None
        assert self._device is not None

        item_ids = self.raw_ids_to_item_ids(raw_poi_ids)
        if not item_ids:
            logger.info("No valid mapped POIs remained for SBR inference.")
            return []

        max_len = int(getattr(self._opt, "len_session", self.config.len_session))
        item_ids = item_ids[-max_len:]
        batch = self._infer_sbr.build_single_sample(session=item_ids, max_len=max_len)
        batch = self._infer_sbr.move_batch_to_device(batch, self._device)
        predictions = self._infer_sbr.predict_topk(
            model=self._model,
            batch=batch,
            k=int(top_k or self.config.model_top_k),
            original_session=item_ids,
            exclude_seen=bool(self.config.exclude_seen),
            item2raw=self.item2raw,
        )

        rows: list[dict[str, Any]] = []
        for row in predictions:
            item_id = int(row["item_id"])
            raw_id = row.get("raw_location_id", self.item2raw.get(item_id))
            if raw_id is None:
                continue
            score = float(row.get("score", 0.0))
            rows.append(
                {
                    "rank": int(row.get("rank", len(rows) + 1)),
                    "raw_poi_id": int(raw_id),
                    "raw_location_id": int(raw_id),
                    "item_id": item_id,
                    "score": score,
                    "sbr_score": score,
                    "spatial_score": None,
                    "semantic_score": None,
                    "final_score": score,
                    "candidate_source": "sbr",
                }
            )
        return _normalize_prediction_rows(rows, self.raw2item)

    def raw_ids_to_item_ids(self, raw_poi_ids: list[int]) -> list[int]:
        self._ensure_mappings_loaded()
        mapped: list[int] = []
        missing: list[int] = []
        for raw_id in raw_poi_ids:
            raw_int = _as_int(raw_id)
            if raw_int is None:
                continue
            item_id = self.raw2item.get(raw_int)
            if item_id is None:
                missing.append(raw_int)
                continue
            mapped.append(int(item_id))
        if missing:
            logger.info(
                "Dropped %s unmapped raw POI IDs before model inference. Examples: %s",
                len(missing),
                missing[:10],
            )
        return mapped

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._ensure_mappings_loaded()
            if not self.config.checkpoint_path.exists():
                raise FileNotFoundError(f"Model checkpoint not found: {self.config.checkpoint_path}")
            if not self.config.src_path.exists():
                raise FileNotFoundError(f"Internal model src not found: {self.config.src_path}")

            _evict_external_module("utils", self.config.src_path)
            _evict_external_module("model_exp30", self.config.src_path)
            infer_sbr = _import_from_model_src(self.config.src_path, "infer_sbr")
            torch = importlib.import_module("torch")
            requested_device = self.config.device
            if requested_device == "cuda" and not torch.cuda.is_available():
                logger.info("CUDA requested but unavailable; using CPU for recommendation model.")
                requested_device = "cpu"
            device = torch.device(requested_device)

            args = Namespace(
                dataset="Gowalla",
                batchSize=1,
                hiddenSize=256,
                lr=0.001,
                lr_dc=0.1,
                lr_dc_step=5,
                l2=1e-5,
                step=1,
                ggnn_layers=None,
                gama=1.7,
                num_attention_heads=4,
                neighbor_n=3,
                seed=2023,
                len_session=self.config.len_session,
                last_k=7,
                l_p=4,
                use_attn_conv="True",
                heads=8,
                dot=True,
            )
            opt = infer_sbr.build_opt_from_args(args)
            infer_sbr.get_dataset_n_node = lambda _dataset: max(self.raw2item.values()) + 1
            model = infer_sbr.load_checkpoint_model(opt, str(self.config.checkpoint_path), device)

            self._infer_sbr = infer_sbr
            self._torch = torch
            self._model = model
            self._opt = opt
            self._device = device
            self._loaded = True
            logger.info("Loaded MG-DSGAT recommendation model from %s", self.config.checkpoint_path)

    def _ensure_mappings_loaded(self) -> None:
        if self.raw2item and self.item2raw:
            return
        with self._lock:
            if self.raw2item and self.item2raw:
                return
            if not self.config.raw2item_path.exists():
                raise FileNotFoundError(f"raw2item mapping not found: {self.config.raw2item_path}")
            if not self.config.item2raw_path.exists():
                raise FileNotFoundError(f"item2raw mapping not found: {self.config.item2raw_path}")
            self.raw2item = {
                int(k): int(v) for k, v in _read_json(self.config.raw2item_path).items()
            }
            self.item2raw = {
                int(k): int(v) for k, v in _read_json(self.config.item2raw_path).items()
            }
            logger.info(
                "Loaded POI ID mappings: raw2item=%s item2raw=%s",
                len(self.raw2item),
                len(self.item2raw),
            )


class SpatialReranker:
    def __init__(self, config: RecommendationConfig, raw2item: dict[int, int]):
        self.config = config
        self.raw2item = raw2item
        self._lock = threading.Lock()
        self._loaded = False
        self._spatial_index = None
        self._expand_candidates = None
        self._rank_by_spatial_fusion = None

    def rerank(
        self,
        history_raw_ids: list[int],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self.config.enable_spatial or not candidates:
            return _normalize_prediction_rows(candidates, self.raw2item)
        try:
            self._ensure_loaded()
            expanded = self._expand_candidates(
                sbr_candidates=candidates,
                history_raw_ids=history_raw_ids,
                spatial_index=self._spatial_index,
                spatial_k=self.config.spatial_k,
                exclude_seen=self.config.exclude_seen,
            )
            ranked = self._rank_by_spatial_fusion(
                expanded,
                alpha_sbr=self.config.alpha_sbr,
                alpha_spatial=self.config.alpha_spatial,
            )
            return _normalize_prediction_rows(ranked, self.raw2item)
        except Exception as exc:
            logger.warning("Spatial reranking skipped: %s", exc)
            return _normalize_prediction_rows(candidates, self.raw2item)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if not self.config.poi_metadata_path.exists():
                raise FileNotFoundError(f"POI metadata not found: {self.config.poi_metadata_path}")
            index_module = _import_from_model_src(self.config.src_path, "spatial.index")
            expansion_module = _import_from_model_src(self.config.src_path, "spatial.expansion")
            fusion_module = _import_from_model_src(self.config.src_path, "fusion.training_free")
            self._spatial_index = index_module.SpatialCandidateIndex(self.config.poi_metadata_path)
            self._expand_candidates = expansion_module.expand_candidates_with_spatial_neighbors
            self._rank_by_spatial_fusion = fusion_module.rank_by_spatial_fusion
            self._loaded = True
            logger.info("Loaded spatial reranker with metadata %s", self.config.poi_metadata_path)


class SemanticReranker:
    def __init__(self, config: RecommendationConfig, raw2item: dict[int, int]):
        self.config = config
        self.raw2item = raw2item
        self._lock = threading.Lock()
        self._loaded = False
        self._embedding_store = None
        self._build_session_embedding = None
        self._build_multi_view_session_embeddings = None
        self._score_candidates = None
        self._score_multiview_candidates = None
        self._rank_by_semantic_fusion = None

    def rerank(
        self,
        history_raw_ids: list[int],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        enabled = bool(self.config.enable_semantic)
        embedding_exists = self.config.semantic_embedding_path.exists()
        manifest_path = self._resolve_manifest_path()
        manifest_exists = manifest_path.exists() if manifest_path is not None else False
        logger.info(
            "Semantic reranking status: enabled=%s embedding_exists=%s manifest_exists=%s candidates=%s",
            enabled,
            embedding_exists,
            manifest_exists,
            len(candidates),
        )
        if not enabled or not candidates:
            logger.info("Semantic reranking skipped; final candidate count=%s", len(candidates))
            return _normalize_prediction_rows(candidates, self.raw2item)

        try:
            self._ensure_loaded(manifest_path)
            history_item_ids = self._raw_ids_to_item_ids(history_raw_ids)
            top_k = self.config.semantic_top_k or len(candidates)
            head = candidates[:top_k]
            tail = candidates[top_k:]

            if self.config.semantic_mode == "multiview":
                scored = self._score_multiview(head, history_item_ids)
            else:
                scored = self._score_single_view(head, history_item_ids)
            ranked = self._rank_by_semantic_fusion(
                scored,
                gamma_base=max(0.0, 1.0 - float(self.config.semantic_weight)),
                semantic_weight=float(self.config.semantic_weight),
                missing_semantic_policy="base_only",
            )
            rows = _normalize_prediction_rows(ranked + tail, self.raw2item)
            logger.info("Semantic reranking succeeded; final candidate count=%s", len(rows))
            return rows
        except Exception as exc:
            logger.warning("Semantic reranking skipped: %s", exc)
            rows = _normalize_prediction_rows(candidates, self.raw2item)
            logger.info("Semantic reranking skipped; final candidate count=%s", len(rows))
            return rows

    def _raw_ids_to_item_ids(self, raw_ids: list[int]) -> list[int]:
        item_ids: list[int] = []
        for raw_id in raw_ids:
            raw_int = _as_int(raw_id)
            if raw_int is None:
                continue
            item_id = self.raw2item.get(raw_int)
            if item_id is not None:
                item_ids.append(int(item_id))
        return item_ids

    def _score_single_view(
        self,
        candidates: list[dict[str, Any]],
        history_item_ids: list[int],
    ) -> list[dict[str, Any]]:
        session_embedding, diagnostics = self._build_session_embedding(
            history_item_ids,
            self._embedding_store,
            strategy="recency_weighted",
            last_n=20,
            decay=0.85,
            view=None,
        )
        if diagnostics.get("status") != "ok":
            logger.info("Semantic session embedding status: %s", diagnostics.get("status"))
        scored, _ = self._score_candidates(
            session_embedding,
            candidates,
            self._embedding_store,
            view=None,
        )
        return scored

    def _score_multiview(
        self,
        candidates: list[dict[str, Any]],
        history_item_ids: list[int],
    ) -> list[dict[str, Any]]:
        views = ["visit_pattern", "location", "category_context"]
        view_weights = {"visit_pattern": 0.3, "location": 0.2, "category_context": 0.5}
        session_embeddings, _ = self._build_multi_view_session_embeddings(
            history_item_ids,
            self._embedding_store,
            views=views,
            strategy="recency_weighted",
            last_n=20,
            decay=0.85,
        )
        scored, _ = self._score_multiview_candidates(
            session_embeddings,
            candidates,
            self._embedding_store,
            view_weights=view_weights,
        )
        return scored

    def _ensure_loaded(self, manifest_path: Path | None) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if not self.config.semantic_embedding_path.exists():
                raise FileNotFoundError(
                    f"Semantic embedding file not found: {self.config.semantic_embedding_path}"
                )

            embedding_cache = _load_module_from_file(
                "_wherenext_semantic_embedding_cache",
                self.config.src_path / "semantic" / "embedding_cache.py",
            )
            session_encoder = _load_module_from_file(
                "_wherenext_semantic_session_encoder",
                self.config.src_path / "semantic" / "session_encoder.py",
            )
            similarity = _load_module_from_file(
                "_wherenext_semantic_similarity",
                self.config.src_path / "semantic" / "similarity.py",
            )
            semantic_fusion = _import_from_model_src(self.config.src_path, "fusion.semantic_fusion")

            if manifest_path is not None and manifest_path.exists():
                embedding_store = embedding_cache.load_embedding_store(
                    self.config.semantic_embedding_path,
                    manifest_path,
                )
            else:
                embedding_store = self._infer_embedding_store(embedding_cache)

            self._embedding_store = embedding_store
            self._build_session_embedding = session_encoder.build_session_embedding
            self._build_multi_view_session_embeddings = (
                session_encoder.build_multi_view_session_embeddings
            )
            self._score_candidates = similarity.score_candidates_by_semantic_similarity
            self._score_multiview_candidates = (
                similarity.score_candidates_by_multiview_semantic_similarity
            )
            self._rank_by_semantic_fusion = semantic_fusion.rank_by_semantic_fusion
            self._loaded = True
            logger.info("Loaded semantic reranker embeddings from %s", self.config.semantic_embedding_path)

    def _infer_embedding_store(self, embedding_cache: ModuleType):
        metadata_rows = self._semantic_metadata_rows()
        torch = importlib.import_module("torch")
        loaded = torch.load(self.config.semantic_embedding_path, map_location="cpu")

        view_embeddings = None
        view_names = None
        default_view = "all"
        if isinstance(loaded, dict) and "embeddings_by_view" in loaded:
            view_embeddings = {
                str(view): matrix.detach().cpu().numpy()
                if hasattr(matrix, "detach")
                else np.asarray(matrix)
                for view, matrix in loaded["embeddings_by_view"].items()
            }
            view_names = [str(view) for view in loaded.get("view_names", view_embeddings.keys())]
            default_view = "all" if "all" in view_embeddings else view_names[0]
            embeddings = view_embeddings[default_view]
        elif hasattr(loaded, "detach"):
            embeddings = loaded.detach().cpu().numpy()
        else:
            embeddings = np.asarray(loaded)

        embeddings = np.asarray(embeddings, dtype=np.float32)
        if embeddings.ndim != 2:
            raise ValueError(f"Semantic embeddings must be rank-2, got {embeddings.shape}")
        if embeddings.shape[0] != len(metadata_rows):
            raise ValueError(
                "Cannot infer semantic manifest: embedding rows "
                f"{embeddings.shape[0]} != metadata rows {len(metadata_rows)}"
            )
        if view_embeddings is not None:
            for view, matrix in view_embeddings.items():
                if np.asarray(matrix).shape[0] != len(metadata_rows):
                    raise ValueError(
                        f"Cannot infer semantic manifest for view {view}: row mismatch"
                    )

        item_id_to_index, raw_location_id_to_index = embedding_cache.build_id_mappings(
            metadata_rows
        )
        manifest = {
            "dataset": "Gowalla",
            "row_count": len(metadata_rows),
            "view": default_view,
            "rows": metadata_rows,
            "manifest_source": "inferred_in_memory",
        }
        return embedding_cache.SemanticEmbeddingStore(
            embeddings=embeddings,
            item_id_to_index=item_id_to_index,
            raw_location_id_to_index=raw_location_id_to_index,
            rows=metadata_rows,
            manifest=manifest,
            view_embeddings=(
                {
                    view: np.asarray(matrix, dtype=np.float32)
                    for view, matrix in view_embeddings.items()
                }
                if view_embeddings is not None
                else None
            ),
            view_names=view_names,
            default_view=default_view,
        )

    def _semantic_metadata_rows(self) -> list[dict[str, Any]]:
        if not self.config.poi_metadata_path.exists():
            raise FileNotFoundError(f"POI metadata not found: {self.config.poi_metadata_path}")
        payload = _read_json(self.config.poi_metadata_path)
        if isinstance(payload, dict):
            iterable = payload.items()
        elif isinstance(payload, list):
            iterable = enumerate(payload)
        else:
            raise ValueError("POI metadata must be a JSON object or list.")

        rows: list[dict[str, Any]] = []
        for index, metadata in iterable:
            if not isinstance(metadata, dict):
                continue
            raw_id = _as_int(
                metadata.get("raw_location_id")
                or metadata.get("raw_poi_id")
                or metadata.get("poi_id")
                or metadata.get("id")
                or index
            )
            if raw_id is None:
                continue
            item_id = _as_int(metadata.get("item_id")) or self.raw2item.get(raw_id)
            if item_id is None:
                continue
            rows.append(
                {
                    "index": len(rows),
                    "item_id": int(item_id),
                    "raw_location_id": int(raw_id),
                }
            )
        return rows

    def _resolve_manifest_path(self) -> Path | None:
        if self.config.semantic_manifest_path is not None:
            return self.config.semantic_manifest_path

        directory = self.config.semantic_embedding_path.parent
        stem = self.config.semantic_embedding_path.stem
        candidates = [
            directory / f"{stem}_manifest.json",
            directory / f"{stem}.manifest.json",
            directory / "semantic_manifest.json",
            directory / "manifest.json",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None
