export type ApiHealthStatus = 'connected' | 'checking' | 'disconnected'

export interface ApiHealthResponse {
  status: string
}

export interface ApiHealthSnapshot {
  status: ApiHealthStatus
  latencyMs: number | null
  lastCheckedAt: string | null
  error: string | null
}
