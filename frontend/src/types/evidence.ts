// Mirror of backend/contracts/evidence.py. Keep the two in sync.

import type { Intent, SteeringControls, TravelMode } from './intent'
import type { GowallaPlace } from './place'

// travel and repeat are route costs: their values are <= 0
export type SignalName =
  | 'habit'
  | 'intent'
  | 'geo'
  | 'novelty'
  | 'semantic_history'
  | 'travel'
  | 'repeat'
export type CandidateSource = 'sbr' | 'spatial' | 'sbr+spatial' | 'intent'
export type StageName =
  | 'intent_parse'
  | 'sbr'
  | 'spatial'
  | 'semantic'
  | 'intent_score'
  | 'route_plan'
  | 'explanation'
  | 'verification'
  | 'routing_api'
export type ExclusionReason =
  | 'not_in_candidate_pool'
  | 'avoided_category'
  | 'over_hop_distance'
  | 'over_time_budget'
  | 'already_visited'
  | 'repeated_category'
  | 'outranked'

export interface Signal {
  raw: number | null
  value: number // the value the fusion used; normalized signals in [0, 1], similarities may be < 0
  weight: number // effective weight in the final linear score
  contribution: number // weight * value; contributions sum to final_score
  rank_alone: number | null
}

export interface PoiFacts {
  raw_poi_id: number
  category_name: string | null
  latitude: number
  longitude: number
  checkins_count: number | null
  users_count: number | null
  photos_count: number | null
}

export interface TravelLeg {
  from_raw_poi_id: number
  distance_km: number
  est_minutes: number | null
  mode: TravelMode
}

export interface IntentMatch {
  matched_want: string[]
  similarity: number | null
  within_budget: boolean
  in_range: number | null // wanted-type POIs within search_radius_km at this step; 0 = none in the data
  search_radius_km: number | null
}

export interface HistoryRelation {
  history_window: number
  same_category_visits: number
  visited_this_poi: boolean
  steps_since_category: number | null
}

export interface EvidenceRecord {
  step: number
  rank: number
  pool_size: number
  candidate_source: CandidateSource
  poi: PoiFacts
  final_score: number
  signals: Partial<Record<SignalName, Signal>>
  top_signal: SignalName
  travel: TravelLeg | null
  intent: IntentMatch | null
  history: HistoryRelation
}

export interface StageStatus {
  stage: StageName
  step: number | null // route step; null for request-level stages
  status: 'ran' | 'skipped' | 'failed'
  latency_ms: number | null
  detail: string | null
}

export interface RouteEvidence {
  schema_version: 'evidence/1'
  request_id: string
  user_id: number
  dataset: string
  backbone: string
  history: PoiFacts[]
  intent: Intent | null
  controls: SteeringControls
  steps: EvidenceRecord[]
  stages: StageStatus[]
}

// Response of POST /api/model/route
export interface RouteResponse {
  rounds: GowallaPlace[][] // candidates per stop; rounds[i][0] is the chosen stop
  evidence: RouteEvidence
}

export interface SignalGap {
  signal: SignalName
  asked: number
  chosen: number
  gap: number // chosen - asked; positive means the chosen POI won on this signal
}

export interface WhyNotEvidence {
  schema_version: 'evidence/1'
  step: number
  asked: PoiFacts
  asked_record: EvidenceRecord | null
  chosen_raw_poi_id: number
  reasons: ExclusionReason[]
  gaps: SignalGap[]
}

export interface ExplanationSentence {
  text: string
  evidence_refs: string[] // paths into RouteEvidence, e.g. "steps[0].travel.distance_km"
}

export interface StepExplanation {
  step: number
  sentences: ExplanationSentence[]
}

export interface GroundedExplanation {
  summary: ExplanationSentence[]
  steps: StepExplanation[]
}

export interface SentenceVerdict {
  step: number | null
  index: number
  verdict: 'supported' | 'unsupported' | 'unverifiable'
  reason: string | null
}

export interface VerifiedExplanation {
  explanation: GroundedExplanation
  verdicts: SentenceVerdict[]
  verifier_version: string
}

// Response of POST /api/chat/grounded; failures come back as a plain message string
export interface GroundedResponse {
  markdown: string // supported and unverifiable sentences, with a check summary
  explanation: VerifiedExplanation
  model: string
}
