"""Interface contracts shared by the frontend, the recommender, and the LLM calls.

intent: what the user asked for (ParsedIntent from the LLM, resolved Intent,
SteeringControls). evidence: what the recommender computed for each suggested
POI (RouteEvidence, WhyNotEvidence) and the grounded explanation built on it.
The TypeScript mirrors live in frontend/src/types/intent.ts and evidence.ts.
"""

from .evidence import (
    EVIDENCE_SCHEMA_VERSION,
    EvidenceRecord,
    GroundedExplanation,
    RouteEvidence,
    StageStatus,
    VerifiedExplanation,
    WhyNotEvidence,
    resolve_ref,
)
from .intent import INTENT_SCHEMA_VERSION, Intent, ParsedIntent, SteeringControls

__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "INTENT_SCHEMA_VERSION",
    "EvidenceRecord",
    "GroundedExplanation",
    "Intent",
    "ParsedIntent",
    "RouteEvidence",
    "StageStatus",
    "SteeringControls",
    "VerifiedExplanation",
    "WhyNotEvidence",
    "resolve_ref",
]
