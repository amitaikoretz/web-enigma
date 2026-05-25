import { readApiError } from './errors'
import type { StrategyMetadata } from '../types/strategies'

export async function fetchStrategies(): Promise<StrategyMetadata[]> {
  const response = await fetch('/api/strategies')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load strategies'))
  }
  return response.json() as Promise<StrategyMetadata[]>
}
