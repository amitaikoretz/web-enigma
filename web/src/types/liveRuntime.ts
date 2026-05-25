export interface WorkerHeartbeat {
  worker_id: string
  pod_name: string
  shard_id: number
  status: string
  owned_symbol_count: number
  updated_at: string
}

export interface ShardAssignment {
  shard_id: number
  symbol_keys: string[]
}

export interface LeaseRecord {
  symbol_key: string
  worker_id: string
  pod_name: string
  shard_id: number
  assignment_version: number
  leased_at: string
  expires_at: string
}

export interface ControlFlags {
  kill_switch_enabled: boolean
  paused_contracts: string[]
  paused_symbols: string[]
  paused_shards: number[]
}

export interface RuntimeState {
  assignment_version: number
  assignments: ShardAssignment[]
  workers: WorkerHeartbeat[]
  leases: LeaseRecord[]
  control_flags: ControlFlags
}

export type WorkerEventSeverity = 'info' | 'warn' | 'error'

export interface WorkerEvent {
  id: string
  worker_id: string
  shard_id: number | null
  contract_id: string | null
  symbol_key: string | null
  event_type: string
  severity: WorkerEventSeverity
  payload: Record<string, unknown>
  created_at: string
}

export interface LiveRuntimeResponse {
  state: RuntimeState
  events: WorkerEvent[]
}
