import '@testing-library/jest-dom/vitest'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { MarketDataResponse } from '../types/marketData'
import { BacktestRunChart } from './BacktestRunChart'

const fetchSymbolBarsMock = vi.hoisted(() => vi.fn())

vi.mock('../api/marketData', () => ({
  fetchSymbolBars: fetchSymbolBarsMock,
}))

vi.mock('./CandlestickChart', () => ({
  CandlestickChart: ({ themeMode }: { themeMode?: string }) => (
    <div data-testid="chart-theme">{themeMode}</div>
  ),
}))

describe('BacktestRunChart', () => {
  const response: MarketDataResponse = {
    symbol: 'AAPL',
    provider: 'alpaca',
    resolution: '1m',
    start_date: '2024-01-01',
    stop_date: '2024-01-01',
    cache_status: 'fresh',
    rows: [
      {
        timestamp: '2024-01-01T09:30:00.000Z',
        open: 100,
        high: 101,
        low: 99,
        close: 100.5,
        volume: 1000,
      },
    ],
  }

  beforeEach(() => {
    fetchSymbolBarsMock.mockReset()
    fetchSymbolBarsMock.mockResolvedValue(response)
  })

  it('lets the user switch the chart theme independently from the app theme', async () => {
    render(
      <ThemeProvider theme={createTheme({ palette: { mode: 'light' } })}>
        <BacktestRunChart
          symbol="AAPL"
          startDate="2024-01-01"
          endDate="2024-01-01"
          resolution="1m"
          orders={[]}
          trades={[]}
        />
      </ThemeProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('chart-theme')).toHaveTextContent('light'))

    fireEvent.click(screen.getByRole('button', { name: /dark chart/i }))

    await waitFor(() => expect(screen.getByTestId('chart-theme')).toHaveTextContent('dark'))
  })
})
