"""Intent contract: what the user asked for, in the form the recommender consumes.

Three layers:
- ParsedIntent: the strict JSON an LLM returns for one natural-language query.
- Intent: ParsedIntent resolved against the dataset's category vocabulary. The
  UI shows it as editable chips, and the recommender scores candidates against it.
- SteeringControls: the habit/intent and explore weights the recommender used.
  They are derived from the intent, not set by end users.

LLM output must be checked with ParsedIntent.model_validate_json before use.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


INTENT_SCHEMA_VERSION = "intent/1"

TravelMode = Literal["walk", "drive", "transit"]
ExplorePreference = Literal["familiar", "balanced", "new"]
IntentStrength = Literal["soft", "firm"]
MatchMethod = Literal["llm_hint", "lexical", "embedding", "user_edit"]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntentPhrase(_Contract):
    """One thing the user wants or wants to avoid, in their own words."""

    phrase: str = Field(min_length=1, description="Span copied from the user's query.")
    category_hints: list[str] = Field(
        default_factory=list,
        description="Names from the provided category vocabulary that fit the phrase; "
        "empty when none fit.",
    )


class ParsedIntent(_Contract):
    """LLM output for one query. Leave a field null when the query does not say it."""

    want: list[IntentPhrase] = Field(default_factory=list)
    avoid: list[IntentPhrase] = Field(default_factory=list)
    strength: IntentStrength | None = Field(
        default=None,
        description="'firm' when the user insists ('must', 'definitely'); "
        "'soft' when they hedge ('maybe', 'something like').",
    )
    num_stops: int | None = Field(default=None, ge=1, le=5)
    time_budget_min: int | None = Field(default=None, ge=10, le=720)
    max_hop_km: float | None = Field(default=None, gt=0, le=50)
    travel_mode: TravelMode | None = None
    explore: ExplorePreference | None = Field(
        default=None,
        description="'new' when the user asks for places unlike their usual ones; "
        "'familiar' when they ask for their usual kind of place.",
    )
    unsupported: list[str] = Field(
        default_factory=list,
        description="Parts of the query the system cannot act on, such as opening hours, "
        "price, or ratings, which the dataset does not contain.",
    )


class CategoryMatch(_Contract):
    """A dataset category that one user phrase resolved to."""

    category_name: str = Field(description="Exact name from the dataset vocabulary.")
    phrase: str = Field(description="The user phrase it was resolved from.")
    method: MatchMethod
    score: float | None = Field(default=None, ge=0, le=1)


class ParserTrace(_Contract):
    model: str
    latency_ms: float = Field(ge=0)
    fallback: bool = Field(description="True when the LLM failed and a keyword parser was used.")


class Intent(_Contract):
    """Resolved intent. Every category here exists in the dataset."""

    schema_version: Literal["intent/1"] = INTENT_SCHEMA_VERSION
    query: str
    source: Literal["llm", "keyword", "user_edit"]
    want: list[CategoryMatch] = Field(default_factory=list)
    avoid: list[CategoryMatch] = Field(default_factory=list)
    strength: IntentStrength = "soft"
    explore: ExplorePreference = "balanced"
    num_stops: int = Field(default=3, ge=1, le=5)
    time_budget_min: int | None = Field(default=None, ge=10, le=720)
    max_hop_km: float | None = Field(default=None, gt=0, le=50)
    travel_mode: TravelMode = "drive"
    unsupported: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(
        default_factory=list,
        description="Want/avoid phrases that matched no dataset category.",
    )
    parser: ParserTrace | None = None


class SteeringControls(_Contract):
    """Weights the recommender used for one request.

    End users never set these. A fixed policy maps the intent's strength and
    explore preference to them; with no intent, ranking uses habit only. The
    inspector view for researchers may override them.
    """

    habit_intent: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="lambda: 0 ranks by habit (SBR) only, 1 by intent only.",
    )
    explore: float = Field(default=0.0, ge=0, le=1, description="epsilon: weight of novelty.")
    source: Literal["default", "intent", "inspector"] = "default"
