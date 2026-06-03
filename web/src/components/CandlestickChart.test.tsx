import '@testing-library/jest-dom/vitest'

import { describe, expect, it } from 'vitest'

import type { MarketDataResponse } from '../types/marketData'
import { getTradingDayBoundaryTimes } from '../utils/tradingDayBoundaries'

describe('getTradingDayBoundaryTimes', () => {
  it('returns the first bar of each new trading day for intraday data', () => {
    const data: MarketDataResponse = {
      symbol: 'AAPL',
      provider: 'alpaca',
      resolution: '1m',
      start_date: '2024-01-01',
      stop_date: '2024-01-03',
      cache_status: 'fresh',
      rows: [
        {
          timestamp: '2024-01-01T14:30:00.000Z',
          open: 100,
          high: 101,
          low: 99,
          close: 100,
          volume: 1000,
        },
        {
          timestamp: '2024-01-01T14:31:00.000Z',
          open: 100,
          high: 101,
          low: 99,
          close: 100,
          volume: 1000,
        },
        {
          timestamp: '2024-01-02T14:30:00.000Z',
          open: 101,
          high: 102,
          low: 100,
          close: 101,
          volume: 1000,
        },
        {
          timestamp: '2024-01-03T14:30:00.000Z',
          open: 102,
          high: 103,
          low: 101,
          close: 102,
          volume: 1000,
        },
      ],
    }

    expect(getTradingDayBoundaryTimes(data, 'America/New_York')).toEqual([
      Math.floor(Date.parse('2024-01-02T14:30:00.000Z') / 1000),
      Math.floor(Date.parse('2024-01-03T14:30:00.000Z') / 1000),
    ])
  })

  it('skips daily resolution data', () => {
    const data: MarketDataResponse = {
      symbol: 'AAPL',
      provider: 'alpaca',
      resolution: '1d',
      start_date: '2024-01-01',
      stop_date: '2024-01-03',
      cache_status: 'fresh',
      rows: [
        {
          timestamp: '2024-01-01T00:00:00.000Z',
          open: 100,
          high: 101,
          low: 99,
          close: 100,
          volume: 1000,
        },
        {
          timestamp: '2024-01-02T00:00:00.000Z',
          open: 101,
          high: 102,
          low: 100,
          close: 101,
          volume: 1000,
        },
      ],
    }

    expect(getTradingDayBoundaryTimes(data, 'America/New_York')).toEqual([])
  })
})
