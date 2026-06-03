import type { Time } from 'lightweight-charts'

import type { MarketDataResponse } from '../types/marketData'
import { toChartTime } from './chartTime'

function getTradingDayKey(timestamp: string, timezone: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(timestamp))
}

export function getTradingDayBoundaryTimes(data: MarketDataResponse, timezone: string): Time[] {
  if (data.resolution === '1d') {
    return []
  }

  const boundaryTimes: Time[] = []
  let previousDayKey: string | null = null

  for (const row of data.rows) {
    const currentDayKey = getTradingDayKey(row.timestamp, timezone)
    if (previousDayKey !== null && currentDayKey !== previousDayKey) {
      boundaryTimes.push(toChartTime(row.timestamp, data.resolution))
    }
    previousDayKey = currentDayKey
  }

  return boundaryTimes
}
