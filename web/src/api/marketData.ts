import dayjs from 'dayjs'

import { readApiError } from './errors'
import type { ChartQuery, MarketDataResponse } from '../types/marketData'

export function computeStopDate(startDate: string, numDays: number): string {
  return dayjs(startDate).add(numDays - 1, 'day').format('YYYY-MM-DD')
}

export async function fetchSymbolBars(query: ChartQuery): Promise<MarketDataResponse> {
  const symbol = query.symbol.trim().toUpperCase()
  if (!symbol) {
    throw new Error('Symbol is required')
  }
  if (query.numDays < 1) {
    throw new Error('Number of days must be at least 1')
  }

  const stopDate = computeStopDate(query.startDate, query.numDays)
  const params = new URLSearchParams({
    start_date: query.startDate,
    stop_date: stopDate,
    resolution: query.resolution,
  })

  const response = await fetch(`/api/symbols/${encodeURIComponent(symbol)}/bars?${params}`)
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Request failed'))
  }

  return response.json() as Promise<MarketDataResponse>
}
