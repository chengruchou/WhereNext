from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from contracts.evidence import EvidenceRecord, RouteEvidence, StageStatus
from contracts.intent import Intent, SteeringControls
from database import POI, UserHist
from services.evidence_builder import build_step_records, poi_facts
from services.intent_signal import IntentScorer
from services.latest_model_adapter import (
    LatestSBRModel,
    SemanticReranker,
    SpatialReranker,
    StageResult,
)
from services.model_config import RecommendationConfig
from services.route_planner import plan_step, route_planning_enabled
from services.steering import PoiIndex, needs_steering, steer


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


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


@dataclass
class StepResult:
    """One recommendation round: returned POIs, their evidence, and stage status."""

    pois: list[dict[str, Any]] = field(default_factory=list)
    records: list[EvidenceRecord] = field(default_factory=list)
    stages: list[StageStatus] = field(default_factory=list)
    session: list[dict[str, Any]] = field(default_factory=list)


class RecommendationService:
    def __init__(self, config: RecommendationConfig | None = None):
        self.config = config or RecommendationConfig.from_env()
        self.sbr_model = LatestSBRModel(self.config)
        self.spatial_reranker: SpatialReranker | None = None
        self.semantic_reranker: SemanticReranker | None = None
        self.poi_index: PoiIndex | None = None
        self.intent_scorer: IntentScorer | None = None

    def recommend_for_user(
        self,
        user_id: int,
        append_back: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self.recommend_step(user_id, append_back, with_evidence=False).pois

    def recommend_step(
        self,
        user_id: int,
        append_back: list[Any] | None = None,
        step: int = 1,
        with_evidence: bool = True,
        intent: Intent | None = None,
        controls: SteeringControls | None = None,
        route_stops: list[int] | None = None,
    ) -> StepResult:
        """One ranking round. route_stops (stops already chosen in this route) turns on
        the route planner; None leaves the ranking as steering produced it."""

        controls = controls or SteeringControls()
        histories = (
            UserHist.query.filter_by(user_id=int(user_id))
            .order_by(UserHist.visit_time)
            .all()
        )
        history_raw_ids = [int(hist.poi_id) for hist in histories if hist.poi_id is not None]
        append_raw_ids = self._valid_append_raw_ids(append_back or [])
        session_raw_ids = history_raw_ids + append_raw_ids
        if not session_raw_ids:
            return StepResult()

        session = self._session_pois(session_raw_ids) if with_evidence else []
        final_rows, stages, steering_ran = self.rank_session(
            session_raw_ids, step=step, intent=intent, controls=controls, route_stops=route_stops
        )
        if not final_rows:
            return StepResult(stages=stages, session=session)

        ranked = self._hydrate_rows(final_rows)
        if not with_evidence:
            return StepResult(pois=[poi for _, poi in ranked], stages=stages)
        records = build_step_records(
            ranked,
            step=step,
            pool=final_rows,
            session=session,
            config=self.config,
            controls=controls if steering_ran else None,
            travel_mode=intent.travel_mode if intent else "drive",
        )
        return StepResult(
            pois=[poi for _, poi in ranked],
            records=records,
            stages=stages,
            session=session,
        )

    def rank_session(
        self,
        session_raw_ids: list[int],
        *,
        step: int = 1,
        intent: Intent | None = None,
        controls: SteeringControls | None = None,
        route_stops: list[int] | None = None,
    ) -> tuple[list[dict[str, Any]], list[StageStatus], bool]:
        """Rank candidates for a session given as raw POI IDs, with no database access, so
        offline evaluation runs the same stages as the app. Returns the ranked rows, the
        stage statuses, and whether steering ran."""

        controls = controls or SteeringControls()
        start = time.perf_counter()
        sbr_rows = self.sbr_model.predict(session_raw_ids, top_k=self.config.model_top_k)
        stages = [StageStatus(stage="sbr", step=step, status="ran", latency_ms=_elapsed_ms(start))]
        if not sbr_rows:
            return [], stages, False

        spatial_rows, spatial_status = self._run_stage(
            "spatial", step, lambda: self._spatial().rerank(session_raw_ids, sbr_rows)
        )
        stages.append(spatial_status)
        semantic_rows, status = self._run_stage(
            "semantic", step, lambda: self._semantic().rerank(session_raw_ids, spatial_rows)
        )
        stages.append(status)

        steered = needs_steering(intent, controls)
        final_rows, status = self._run_stage(
            "intent_score",
            step,
            lambda: self._steer(
                semantic_rows,
                intent=intent,
                controls=controls,
                session_raw_ids=session_raw_ids,
                spatial_ran=spatial_status.status == "ran",
            ),
        )
        stages.append(status)
        steering_ran = steered and status.status == "ran"

        if route_stops is not None:
            final_rows, status = self._run_stage(
                "route_plan",
                step,
                lambda: self._plan(
                    final_rows,
                    route_stops=route_stops,
                    session_raw_ids=session_raw_ids,
                    intent=intent,
                    controls=controls,
                ),
            )
            stages.append(status)
        return final_rows, stages, steering_ran

    def recommend_route(
        self,
        user_id: int,
        append_back: list[Any] | None = None,
        num_stops: int = 3,
        intent: Intent | None = None,
        controls: SteeringControls | None = None,
    ) -> tuple[list[list[dict[str, Any]]], RouteEvidence]:
        """Greedy route: each round re-ranks with the route so far, appends its top POI,
        and runs again; the route planner adds travel and repeat costs."""

        controls = controls or SteeringControls()
        extra = list(append_back or [])
        chosen: list[int] = []
        rounds: list[list[dict[str, Any]]] = []
        steps: list[EvidenceRecord] = []
        stages: list[StageStatus] = []
        history: list[dict[str, Any]] | None = None
        for step in range(1, num_stops + 1):
            result = self.recommend_step(
                user_id,
                extra,
                step=step,
                intent=intent,
                controls=controls,
                route_stops=list(chosen),
            )
            stages.extend(result.stages)
            if history is None:
                history = result.session
            if not result.pois:
                break
            rounds.append(result.pois)
            steps.append(result.records[0])
            extra.append(result.pois[0]["raw_poi_id"])
            chosen.append(int(result.pois[0]["raw_poi_id"]))

        evidence = RouteEvidence(
            request_id=uuid.uuid4().hex,
            user_id=int(user_id),
            dataset=self.config.raw2item_path.parent.name.lower(),
            backbone=self.config.model_repo.name,
            history=[poi_facts(poi) for poi in history or []],
            intent=intent,
            controls=controls,
            steps=steps,
            stages=stages,
        )
        return rounds, evidence

    def _steer(
        self,
        rows: list[dict[str, Any]],
        *,
        intent: Intent | None,
        controls: SteeringControls,
        session_raw_ids: list[int],
        spatial_ran: bool,
    ) -> StageResult:
        if not needs_steering(intent, controls):
            return rows, "skipped", "no intent"
        if not rows:
            return rows, "skipped", "no candidates"
        try:
            scorer = self._intent_scorer()
            steered, detail = steer(
                rows,
                intent=intent,
                controls=controls,
                session_ids=session_raw_ids,
                index=self._poi_index(),
                raw2item=self.sbr_model.raw2item,
                config=self.config,
                spatial_ran=spatial_ran,
                intent_scores=scorer.score(intent),
                signal_method=scorer.method,
                habit_scores=lambda raw_ids: self._habit_scores(session_raw_ids, raw_ids),
            )
            return steered, "ran", detail
        except Exception as exc:
            logger.warning("Intent steering failed: %s", exc)
            return rows, "failed", str(exc)

    def _habit_scores(self, session_raw_ids: list[int], raw_ids: list[int]) -> dict[int, float]:
        # A failure here keeps the pipeline's habit values instead of failing the stage.
        try:
            return self.sbr_model.score(session_raw_ids, raw_ids)
        except Exception as exc:
            logger.warning("Habit scoring within the request failed: %s", exc)
            return {}

    def _plan(
        self,
        rows: list[dict[str, Any]],
        *,
        route_stops: list[int],
        session_raw_ids: list[int],
        intent: Intent | None,
        controls: SteeringControls,
    ) -> StageResult:
        if not route_planning_enabled(self.config):
            return rows, "skipped", "disabled"
        if not rows:
            return rows, "skipped", "no candidates"
        try:
            planned, detail = plan_step(
                rows,
                route_stops=route_stops,
                session_ids=session_raw_ids,
                index=self._poi_index(),
                config=self.config,
                intent=intent,
                controls=controls,
            )
            return planned, "ran", detail
        except Exception as exc:
            logger.warning("Route planning failed: %s", exc)
            return rows, "failed", str(exc)

    def _poi_index(self) -> PoiIndex:
        if self.poi_index is None:
            self.poi_index = PoiIndex.from_metadata(self.config.poi_metadata_path)
        return self.poi_index

    def _intent_scorer(self) -> IntentScorer:
        if self.intent_scorer is None:
            categories = list(self._poi_index().by_category)
            self.intent_scorer = IntentScorer(self.config.intent_encoder, categories)
        return self.intent_scorer

    def _run_stage(
        self,
        stage: str,
        step: int,
        run: Callable[[], StageResult],
    ) -> tuple[list[dict[str, Any]], StageStatus]:
        start = time.perf_counter()
        rows, status, detail = run()
        return rows, StageStatus(
            stage=stage,
            step=step,
            status=status,
            latency_ms=_elapsed_ms(start),
            detail=detail,
        )

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

    def _session_pois(self, raw_ids: list[int]) -> list[dict[str, Any]]:
        pois = POI.query.filter(POI.id.in_(set(raw_ids))).all()
        poi_by_id = {int(poi.id): poi.to_dict() for poi in pois}
        return [poi_by_id[raw_id] for raw_id in raw_ids if raw_id in poi_by_id]

    def _hydrate_rows(
        self,
        prediction_rows: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """Pair each returned row with its POI record, in final order."""

        ordered: list[tuple[int, dict[str, Any]]] = []
        seen: set[int] = set()
        for row in prediction_rows:
            raw_id = _extract_raw_poi_id(row)
            if raw_id is None or raw_id in seen:
                continue
            seen.add(raw_id)
            ordered.append((raw_id, row))

        if not ordered:
            return []

        pois = POI.query.filter(POI.id.in_([raw_id for raw_id, _ in ordered])).all()
        poi_by_id = {
            int(poi.id): poi.to_dict()
            for poi in pois
            if poi.cat_name != ""
        }
        return [
            (row, poi_by_id[raw_id])
            for raw_id, row in ordered
            if raw_id in poi_by_id
        ][: self.config.return_top_k]


_service: RecommendationService | None = None


def get_recommendation_service() -> RecommendationService:
    global _service
    if _service is None:
        _service = RecommendationService()
    return _service
