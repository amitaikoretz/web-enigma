export type MarketOverviewStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface MarketOverviewIndicator {
  key: string
  label: string
  value: string
  change?: string | null
  tone?: 'positive' | 'negative' | 'neutral' | 'warning' | 'info'
  category?: string | null
  note?: string | null
  explanation?: MarketOverviewIndicatorExplanation | null
}

export interface MarketOverviewIndicatorExplanation {
  summary: string
  inputs: string[]
  calculation_steps: string[]
  interpretation: string
  freshness?: string | null
  caveats: string[]
}

export interface MarketOverviewMethodology {
  summary: string
  inputs: string[]
  scoring: string[]
  freshness?: string | null
  caveats: string[]
}

export interface MarketOverviewSnapshot {
  snapshot_id: string
  name?: string | null
  status: MarketOverviewStatus
  argo_namespace?: string | null
  argo_workflow_name?: string | null
  as_of?: string | null
  top_regime?: string | null
  probabilities: Record<string, number>
  confidence: number
  fragility: number
  contradiction_score: number
  market_indicators: MarketOverviewIndicator[]
  pillar_scores: Record<string, unknown>
  developments: Array<Record<string, unknown>>
  freshness: Record<string, unknown>
  summary_text?: string | null
  watch_next: string[]
  methodology?: MarketOverviewMethodology | null
  evidence: Record<string, unknown>
  params: Record<string, unknown>
  error_message?: string | null
  created_at: string
  updated_at: string
}

export interface MarketOverviewListResponse {
  items: MarketOverviewSnapshot[]
}

export interface MarketOverviewLaunchResponse {
  snapshot_id: string
  status: MarketOverviewStatus
  argo_namespace: string
  argo_workflow_name: string
}
