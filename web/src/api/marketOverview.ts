import { readApiError } from './errors'
import type {
  MarketOverviewListResponse,
  MarketOverviewSnapshot,
  MarketOverviewLaunchResponse,
} from '../types/marketOverview'

export async function fetchMarketOverview(): Promise<MarketOverviewListResponse> {
  const response = await fetch('/api/market-overview')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load market overview'))
  }
  return response.json() as Promise<MarketOverviewListResponse>
}

export async function fetchLatestMarketOverview(): Promise<MarketOverviewSnapshot> {
  const response = await fetch('/api/market-overview/latest')
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to load latest market overview'))
  }
  return response.json() as Promise<MarketOverviewSnapshot>
}

export async function launchMarketOverview(): Promise<MarketOverviewLaunchResponse> {
  const response = await fetch('/api/market-overview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to launch market overview'))
  }
  return response.json() as Promise<MarketOverviewLaunchResponse>
}
