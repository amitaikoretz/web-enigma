export type SymbolUniverse = {
  key: string
  kind: string | null
  name: string
  description: string | null
  provider: string | null
  provider_ref: Record<string, unknown>
  is_active: boolean
  latest_refresh_status: string | null
  latest_refresh_started_at: string | null
  latest_refresh_as_of: string | null
}

export type SymbolUniverseConstituents = {
  key: string
  as_of: string
  symbols: string[]
}
