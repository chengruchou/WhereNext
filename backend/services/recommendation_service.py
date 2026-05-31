from __future__ import annotations

import logging
from typing import Any

from database import POI, UserHist
from services.latest_model_adapter import LatestSBRModel, SemanticReranker, SpatialReranker
from services.model_config import RecommendationConfig


logger = logging.getLogger(__name__)


def _extract_raw_poi_id(value: Any) -> int | None:
    if isinstance(value, dict):
        for key in ("raw_poi_id", "raw_location_id", "poi_id", "id"):
            if key in value:
                return _extract_raw_poi_id(value[key])
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class RecommendationService:
    def __init__(self, config: RecommendationConfig | None = None):
        self.config = config or RecommendationConfig.from_env()
        self.sbr_model = LatestSBRModel(self.config)
        self.spatial_reranker: SpatialReranker | None = None
        self.semantic_reranker: SemanticReranker | None = None

    def recommend_for_user(
        self,
        user_id: int,
        append_back: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        histories = (
            UserHist.query.filter_by(user_id=int(user_id))
            .order_by(UserHist.visit_time)
            .all()
        )
        history_raw_ids = [int(hist.poi_id) for hist in histories if hist.poi_id is not None]
        append_raw_ids = self._valid_append_raw_ids(append_back or [])
        session_raw_ids = history_raw_ids + append_raw_ids
        if not session_raw_ids:
            return []

        sbr_rows = self.sbr_model.predict(session_raw_ids, top_k=self.config.model_top_k)
        if not sbr_rows:
            return []

        spatial_rows = self._spatial().rerank(session_raw_ids, sbr_rows)
        semantic_rows = self._semantic().rerank(session_raw_ids, spatial_rows)
        return self._hydrate_pois(semantic_rows)

    def _valid_append_raw_ids(self, append_back: list[Any]) -> list[int]:
        raw_ids: list[int] = []
        for value in append_back:
            raw_id = _extract_raw_poi_id(value)
            if raw_id is None:
                continue
            if POI.query.get(raw_id) is None:
                logger.info("Ignoring append_back POI not found in DB: %s", raw_id)
                continue
            raw_ids.append(int(raw_id))
        return raw_ids

    def _spatial(self) -> SpatialReranker:
        if self.spatial_reranker is None:
            self.spatial_reranker = SpatialReranker(self.config, self.sbr_model.raw2item)
        return self.spatial_reranker

    def _semantic(self) -> SemanticReranker:
        if self.semantic_reranker is None:
            self.semantic_reranker = SemanticReranker(self.config, self.sbr_model.raw2item)
        return self.semantic_reranker

    def _hydrate_pois(self, prediction_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered_raw_ids: list[int] = []
        seen: set[int] = set()
        for row in prediction_rows:
            raw_id = _extract_raw_poi_id(row)
            if raw_id is None or raw_id in seen:
                continue
            seen.add(raw_id)
            ordered_raw_ids.append(raw_id)

        if not ordered_raw_ids:
            return []

        pois = POI.query.filter(POI.id.in_(ordered_raw_ids)).all()
        poi_by_id = {
            int(poi.id): poi.to_dict()
            for poi in pois
            if poi.cat_name != ""
        }
        return [
            poi_by_id[raw_id]
            for raw_id in ordered_raw_ids
            if raw_id in poi_by_id
        ][: self.config.return_top_k]


_service: RecommendationService | None = None


def get_recommendation_service() -> RecommendationService:
    global _service
    if _service is None:
        _service = RecommendationService()
    return _service
