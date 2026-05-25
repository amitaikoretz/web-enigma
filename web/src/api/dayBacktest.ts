import { readApiError } from './errors'
import type { SingleDayBacktestQuery, SingleDayBacktestResponse } from '../types/dayBacktest'

export async function runSingleDayBacktest(
  query: SingleDayBacktestQuery,
): Promise<SingleDayBacktestResponse> {
  const symbol = query.symbol.trim().toUpperCase()
  if (!symbol) {
    throw new Error('Symbol is required')
  }
  if (!query.strategy) {
    throw new Error('Strategy is required')
  }

  const response = await fetch('/api/backtests/single-day', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol,
      date: query.date,
      resolution: query.resolution,
      strategy: query.strategy,
      strategy_params: query.strategyParams,
    }),
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, 'Backtest request failed'))
  }

  return response.json() as Promise<SingleDayBacktestResponse>
}
