import type { BacktestTradeRecord } from '../types/backtests'

export interface TradeChartFocusWindowMs {
  fromMs: number
  toMs: number
}

const DEFAULT_PADDING_MINUTES = 10
const MINUTE_MS = 60_000

function parseFirstValidTimestamp(values: Array<string | null | undefined>): number | null {
  for (const value of values) {
    if (!value) {
      continue
    }

    const parsed = Date.parse(value)
    if (!Number.isNaN(parsed)) {
      return parsed
    }
  }

  return null
}

export function buildTradeChartFocusWindowMs(
  trade: BacktestTradeRecord,
  paddingMinutes = DEFAULT_PADDING_MINUTES,
): TradeChartFocusWindowMs | null {
  const paddingMs = paddingMinutes * MINUTE_MS
  const fromMs = parseFirstValidTimestamp([trade.entry_datetime, trade.datetime])
  const toMs = parseFirstValidTimestamp([trade.datetime, trade.entry_datetime])

  if (fromMs === null || toMs === null) {
    return null
  }

  return {
    fromMs: fromMs - paddingMs,
    toMs: toMs + paddingMs,
  }
}

export function clampTradeChartFocusWindowMs(
  window: TradeChartFocusWindowMs,
  dataRange: TradeChartFocusWindowMs,
): TradeChartFocusWindowMs | null {
  const fromMs = Math.max(window.fromMs, dataRange.fromMs)
  const toMs = Math.min(window.toMs, dataRange.toMs)

  if (toMs <= fromMs) {
    return null
  }

  return { fromMs, toMs }
}
