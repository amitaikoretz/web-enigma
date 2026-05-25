import { readApiError } from './errors'
import type { LiveRuntimeResponse } from '../types/liveRuntime'

export interface LiveRuntimeFilters {
  limit?: number
  worker_id?: string
  event_type?: string
  symbol_key?: string
}

export async function fetchLiveRuntime(
  filters: LiveRuntimeFilters = {},
): Promise<LiveRuntimeResponse> {
  const params = new URLSearchParams()
  if (filters.limit !== undefined) {
    params.set('limit', String(filters.limit))
  }
  if (filters.worker_id) {
    params.set('worker_id', filters.worker_id)
  }
  if (filters.event_type) {
    params.set('event_type', filters.event_type)
  }
  if (filters.symbol_key) {
    params.set('symbol_key', filters.symbol_key)
  }
  const query = params.toString()
  const response = await fetch(`/api/live/runtime${query ? `?${query}` : ''}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load runtime'))
  }
  return response.json() as Promise<LiveRuntimeResponse>
}
