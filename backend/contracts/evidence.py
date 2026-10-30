"""Evidence contract: what the recommender computed for each suggested POI.

The evidence JSON (RouteEvidence) is the only input the explanation LLM sees.
Each explanation sentence must cite paths into that JSON, and the verifier
checks the sentence against the values those paths point to. Anything missing
from the record, such as ratings, opening hours or prices, cannot be claimed.

Signal weights are effective weights in one linear score, so for every record
the contributions sum to final_score. The current pipeline nests its fusions
(semantic over spatial over SBR); flatten them before filling a record.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .intent import Intent, SteeringControls, TravelMode


EVIDENCE_SCHEMA_VERSION = "evidence/1"
_TOLERANCE = 1e-6

SignalName = Literal["habit", "intent", "geo", "novelty", "semantic_history", "travel", "repeat"]
CandidateSource = Literal["sbr", "spatial", "sbr+spatial", "intent"]
StageName = Literal[
    "intent_parse",
    "sbr",
    "spatial",
    "semantic",
    "intent_score",
    "route_plan",
    "explanation",
    "verification",
    "routing_api",
]
ExclusionReason = Literal[
    "not_in_candidate_pool",
    "avoided_category",
    "over_hop_distance",
    "over_time_budget",
    "already_visited",
    "repeated_category",
    "outranked",
]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Signal(_Contract):
    """One ranking signal for one POI.

    habit: normalized SBR score. geo: 1 / (1 + km) from the spatial stage.
    semantic_history: similarity to the user's history profile.
    intent: similarity to the stated intent. novelty: distance from history categories.
    travel and repeat are route costs with negative values: travel is minus the hop
    length over the route's distance scale, repeat is -1 for a category already in
    the route.
    """

    raw: float | None = Field(
        default=None, description="Before normalization, e.g. SBR score or km."
    )
    value: float = Field(
        ge=-1,
        le=1,
        description="The value the fusion used. Normalized signals lie in [0, 1]; "
        "similarities may be negative.",
    )
    weight: float = Field(ge=0, description="Effective weight in the final linear score.")
    contribution: float = Field(description="weight * value.")
    rank_alone: int | None = Field(
        default=None, ge=1, description="Rank if the pool were sorted by this signal only."
    )

    @model_validator(mode="after")
    def _contribution_matches(self) -> Signal:
        if not math.isclose(self.contribution, self.weight * self.value, abs_tol=_TOLERANCE):
            raise ValueError("contribution must equal weight * value")
        return self


class PoiFacts(_Contract):
    """The only POI metadata an explanation may cite."""

    raw_poi_id: int
    category_name: str | None
    latitude: float
    longitude: float
    checkins_count: int | None = None
    users_count: int | None = None
    photos_count: int | None = None


class TravelLeg(_Contract):
    from_raw_poi_id: int = Field(
        description="Previous route stop, or the last history visit for the first step."
    )
    distance_km: float = Field(ge=0, description="Great-circle distance.")
    est_minutes: float | None = Field(default=None, ge=0, description="From the routing API.")
    mode: TravelMode


class IntentMatch(_Contract):
    matched_want: list[str] = Field(
        default_factory=list, description="Category names from Intent.want that this POI has."
    )
    similarity: float | None = Field(default=None, ge=-1, le=1)
    within_budget: bool = True
    in_range: int | None = Field(
        default=None,
        ge=0,
        description="POIs of the wanted types within search_radius_km of the previous stop "
        "at this step; 0 means the data has none to offer there.",
    )
    search_radius_km: float | None = Field(default=None, gt=0)


class HistoryRelation(_Contract):
    history_window: int = Field(ge=0, description="History visits considered.")
    same_category_visits: int = Field(ge=0)
    visited_this_poi: bool
    steps_since_category: int | None = Field(
        default=None, ge=1, description="How many visits ago this category last appeared."
    )


class EvidenceRecord(_Contract):
    """Everything computed for one POI at one route step."""

    step: int = Field(ge=1)
    rank: int = Field(ge=1, description="Final rank among the candidates at this step.")
    pool_size: int = Field(ge=1)
    candidate_source: CandidateSource
    poi: PoiFacts
    final_score: float
    signals: dict[SignalName, Signal] = Field(min_length=1)
    top_signal: SignalName = Field(description="Signal with the largest contribution.")
    travel: TravelLeg | None = None
    intent: IntentMatch | None = None
    history: HistoryRelation

    @model_validator(mode="after")
    def _score_is_decomposed(self) -> EvidenceRecord:
        total = sum(signal.contribution for signal in self.signals.values())
        if not math.isclose(total, self.final_score, abs_tol=_TOLERANCE):
            raise ValueError("signal contributions must sum to final_score")
        top = max(self.signals, key=lambda name: self.signals[name].contribution)
        if self.top_signal != top:
            raise ValueError(f"top_signal must be {top!r}")
        return self


class StageStatus(_Contract):
    """Whether a pipeline stage ran. A stage must never fail silently."""

    stage: StageName
    step: int | None = Field(default=None, ge=1, description="Route step; None for request-level.")
    status: Literal["ran", "skipped", "failed"]
    latency_ms: float | None = Field(default=None, ge=0)
    detail: str | None = Field(default=None, description="Why it was skipped or how it failed.")


class RouteEvidence(_Contract):
    """Response-level evidence for one recommendation request."""

    schema_version: Literal["evidence/1"] = EVIDENCE_SCHEMA_VERSION
    request_id: str
    user_id: int
    dataset: str
    backbone: str
    history: list[PoiFacts] = Field(
        description="Trajectory the recommender saw, after user edits, oldest first."
    )
    intent: Intent | None = None
    controls: SteeringControls
    steps: list[EvidenceRecord]
    stages: list[StageStatus]


class SignalGap(_Contract):
    signal: SignalName
    asked: float = Field(description="Contribution for the POI the user asked about.")
    chosen: float = Field(description="Contribution for the POI recommended at that step.")
    gap: float = Field(description="chosen - asked; positive means the chosen POI won here.")


class WhyNotEvidence(_Contract):
    """Answer to "why not this POI?" for one route step."""

    schema_version: Literal["evidence/1"] = EVIDENCE_SCHEMA_VERSION
    step: int = Field(ge=1)
    asked: PoiFacts
    asked_record: EvidenceRecord | None = Field(
        default=None, description="None when the POI could not be scored."
    )
    chosen_raw_poi_id: int
    reasons: list[ExclusionReason] = Field(min_length=1)
    gaps: list[SignalGap] = Field(default_factory=list)


class ExplanationSentence(_Contract):
    text: str = Field(min_length=1)
    evidence_refs: list[str] = Field(
        min_length=1,
        description="Paths into the RouteEvidence JSON, 0-based, e.g. "
        "'steps[0].history.same_category_visits'.",
    )


class StepExplanation(_Contract):
    step: int = Field(ge=1)
    sentences: list[ExplanationSentence] = Field(min_length=1)


class GroundedExplanation(_Contract):
    """LLM output for a route explanation. Every sentence cites evidence."""

    summary: list[ExplanationSentence] = Field(min_length=1)
    steps: list[StepExplanation]


class SentenceVerdict(_Contract):
    step: int | None = Field(description="None for summary sentences.")
    index: int = Field(ge=0)
    verdict: Literal["supported", "unsupported", "unverifiable"]
    reason: str | None = None


class VerifiedExplanation(_Contract):
    explanation: GroundedExplanation
    verdicts: list[SentenceVerdict]
    verifier_version: str


_REF_SEGMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)((?:\[\d+\])*)$")


def resolve_ref(evidence: dict[str, Any], path: str) -> Any:
    """Return the value a ref points to in RouteEvidence JSON; raise KeyError if none."""

    node: Any = evidence
    for segment in path.split("."):
        match = _REF_SEGMENT.match(segment)
        if match is None or not isinstance(node, dict) or match.group(1) not in node:
            raise KeyError(path)
        node = node[match.group(1)]
        for index in re.findall(r"\[(\d+)\]", match.group(2)):
            if not isinstance(node, list) or int(index) >= len(node):
                raise KeyError(path)
            node = node[int(index)]
    return node
