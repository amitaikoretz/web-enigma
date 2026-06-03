import { describe, expect, it } from 'vitest'

import type { BacktestTradeRecord } from '../types/backtests'
import {
  buildTradeChartFocusWindowMs,
  clampTradeChartFocusWindowMs,
} from './backtestChartFocus'

function makeTrade(overrides: Partial<BacktestTradeRecord> = {}): BacktestTradeRecord {
  return {
    datetime: '2024-01-02T10:30:00.000Z',
    size: 1,
    price: 100,
    value: 100,
    pnl: 1,
    pnlcomm: 0.9,
    reason: 'take_profit',
    entry_datetime: '2024-01-02T10:00:00.000Z',
    hold_minutes: 30,
    hold_bars: 6,
    ...overrides,
  }
}

describe('backtest chart focus helpers', () => {
  it('pads the trade lifecycle by ten minutes on both sides', () => {
    const focusWindow = buildTradeChartFocusWindowMs(makeTrade())

    expect(focusWindow).toEqual({
      fromMs: Date.parse('2024-01-02T09:50:00.000Z'),
      toMs: Date.parse('2024-01-02T10:40:00.000Z'),
    })
  })

  it('falls back to whichever timestamp is available', () => {
    const entryMissing = buildTradeChartFocusWindowMs(
      makeTrade({
        entry_datetime: null,
      }),
    )
    const exitMissing = buildTradeChartFocusWindowMs(
      makeTrade({
        datetime: null,
      }),
    )

    expect(entryMissing).toEqual({
      fromMs: Date.parse('2024-01-02T10:20:00.000Z'),
      toMs: Date.parse('2024-01-02T10:40:00.000Z'),
    })
    expect(exitMissing).toEqual({
      fromMs: Date.parse('2024-01-02T09:50:00.000Z'),
      toMs: Date.parse('2024-01-02T10:10:00.000Z'),
    })
  })

  it('clamps the requested window to the available data range', () => {
    const focusWindow = buildTradeChartFocusWindowMs(makeTrade())!
    const clamped = clampTradeChartFocusWindowMs(focusWindow, {
      fromMs: Date.parse('2024-01-02T09:55:00.000Z'),
      toMs: Date.parse('2024-01-02T10:35:00.000Z'),
    })

    expect(clamped).toEqual({
      fromMs: Date.parse('2024-01-02T09:55:00.000Z'),
      toMs: Date.parse('2024-01-02T10:35:00.000Z'),
    })
  })
})
