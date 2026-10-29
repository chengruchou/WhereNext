// Mirror of backend/contracts/intent.py. Keep the two in sync.

export type TravelMode = 'walk' | 'drive' | 'transit'
export type ExplorePreference = 'familiar' | 'balanced' | 'new'
export type MatchMethod = 'llm_hint' | 'lexical' | 'embedding' | 'user_edit'
export type IntentStrength = 'soft' | 'firm'

export interface IntentPhrase {
  phrase: string
  category_hints: string[]
}

export interface ParsedIntent {
  want: IntentPhrase[]
  avoid: IntentPhrase[]
  strength: IntentStrength | null
  num_stops: number | null
  time_budget_min: number | null
  max_hop_km: number | null
  travel_mode: TravelMode | null
  explore: ExplorePreference | null
  unsupported: string[]
}

export interface CategoryMatch {
  category_name: string
  phrase: string
  method: MatchMethod
  score: number | null
}

export interface ParserTrace {
  model: string
  latency_ms: number
  fallback: boolean
}

export interface Intent {
  schema_version: 'intent/1'
  query: string
  source: 'llm' | 'keyword' | 'user_edit'
  want: CategoryMatch[]
  avoid: CategoryMatch[]
  strength: IntentStrength
  explore: ExplorePreference
  num_stops: number
  time_budget_min: number | null
  max_hop_km: number | null
  travel_mode: TravelMode
  unsupported: string[]
  unresolved: string[]
  parser: ParserTrace | null
}

// Weights the recommender used. Derived from the intent; end users never set them.
export interface SteeringControls {
  habit_intent: number // lambda in [0, 1]: 0 = habit (SBR) only, 1 = intent only
  explore: number // epsilon in [0, 1]: weight of novelty
  source: 'default' | 'intent' | 'inspector'
}

// Response of POST /api/intent/parse
export interface IntentParseResponse {
  intent: Intent
  controls: SteeringControls
}
