from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_REPO = BACKEND_ROOT / "model_core" / "MG-DSGAT"


def _env_path(name: str, default: Path | None = None) -> Path | None:
    value = os.getenv(name)
    if value:
        return Path(value).expanduser()
    return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class RecommendationConfig:
    model_repo: Path
    src_path: Path
    checkpoint_path: Path
    raw2item_path: Path
    item2raw_path: Path
    poi_metadata_path: Path
    semantic_embedding_path: Path
    semantic_manifest_path: Path | None
    device: str
    model_top_k: int
    return_top_k: int
    len_session: int
    exclude_seen: bool
    enable_spatial: bool
    spatial_k: int
    alpha_sbr: float
    alpha_spatial: float
    enable_semantic: bool
    semantic_top_k: int
    semantic_weight: float
    semantic_mode: str

    @classmethod
    def from_env(cls) -> "RecommendationConfig":
        model_repo = _env_path("WHERENEXT_MODEL_REPO", DEFAULT_MODEL_REPO)
        assert model_repo is not None
        model_repo = model_repo.resolve()

        semantic_manifest = _env_path("WHERENEXT_SEMANTIC_MANIFEST_PATH")
        return cls(
            model_repo=model_repo,
            src_path=(model_repo / "src").resolve(),
            checkpoint_path=_env_path(
                "WHERENEXT_MODEL_CHECKPOINT",
                model_repo / "checkpoints" / "weight.pt",
            ).resolve(),
            raw2item_path=_env_path(
                "WHERENEXT_RAW2ITEM_JSON",
                model_repo / "datasets" / "Gowalla" / "raw_location2item.json",
            ).resolve(),
            item2raw_path=_env_path(
                "WHERENEXT_ITEM2RAW_JSON",
                model_repo / "datasets" / "Gowalla" / "item2raw_location.json",
            ).resolve(),
            poi_metadata_path=_env_path(
                "WHERENEXT_POI_METADATA_JSON",
                model_repo / "datasets" / "Gowalla" / "filtered_poi_metadata.json",
            ).resolve(),
            semantic_embedding_path=_env_path(
                "WHERENEXT_SEMANTIC_EMBEDDING_PATH",
                model_repo / "artifact" / "Gowalla" / "poi_semantic_embeddings.pt",
            ).resolve(),
            semantic_manifest_path=(
                semantic_manifest.resolve() if semantic_manifest is not None else None
            ),
            device=os.getenv("WHERENEXT_DEVICE", "cuda"),
            model_top_k=max(1, _env_int("WHERENEXT_MODEL_TOP_K", 20)),
            return_top_k=max(1, _env_int("WHERENEXT_RETURN_TOP_K", 5)),
            len_session=max(1, _env_int("WHERENEXT_LEN_SESSION", 50)),
            exclude_seen=_env_bool("WHERENEXT_EXCLUDE_SEEN", True),
            enable_spatial=_env_bool("WHERENEXT_ENABLE_SPATIAL", True),
            spatial_k=max(0, _env_int("WHERENEXT_SPATIAL_K", 20)),
            alpha_sbr=_env_float("WHERENEXT_ALPHA_SBR", 0.9),
            alpha_spatial=_env_float("WHERENEXT_ALPHA_SPATIAL", 0.1),
            enable_semantic=_env_bool("WHERENEXT_ENABLE_SEMANTIC", True),
            semantic_top_k=max(0, _env_int("WHERENEXT_SEMANTIC_TOP_K", 20)),
            semantic_weight=_env_float("WHERENEXT_SEMANTIC_WEIGHT", 0.1),
            semantic_mode=os.getenv("WHERENEXT_SEMANTIC_MODE", "single").strip().lower(),
        )
