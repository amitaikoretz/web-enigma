import '@testing-library/jest-dom/vitest'

import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/react'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { BacktestRunResult, BacktestSelectionSummary } from '../types/backtests'
import { BacktestRunDetailPanel } from './BacktestRunDetailPanel'
import { defaultPlatformSettings } from '../settings/defaults'

const useSettingsMock = vi.hoisted(() => vi.fn())

vi.mock('../settings/useSettings', () => ({
  useSettings: useSettingsMock,
}))

vi.mock('./BacktestRunChart', () => ({
  BacktestRunChart: ({
    focusWindow,
    onResetFocusWindow,
  }: {
    focusWindow?: { fromMs: number; toMs: number } | null
    onResetFocusWindow?: () => void
  }) => (
    <div>
      <div data-testid="chart-focus">{focusWindow ? `${focusWindow.fromMs}:${focusWindow.toMs}` : 'none'}</div>
      {onResetFocusWindow ? (
        <button type="button" onClick={onResetFocusWindow}>
          reset chart
        </button>
      ) : null}
    </div>
  ),
}))

function makeResult(): BacktestRunResult {
  return {
    run_id: 'run-1',
    name: 'Sample run',
    status: 'success',
    strategy: 'mean_reversion',
    symbol: 'AAPL',
    data_source: 'alpaca',
    summary: {
      start_value: 10000,
      end_value: 10250,
      return_pct: 2.5,
      max_drawdown_pct: -1.25,
      sharpe_ratio: 1.4,
      total_trades: 1,
      won_trades: 1,
      lost_trades: 0,
    },
    analyzers: {},
    orders: [],
    trades: [
      {
        entry_datetime: '2024-01-02T10:00:00.000Z',
        datetime: '2024-01-02T10:30:00.000Z',
        size: 1,
        price: 100,
        value: 100,
        pnl: 1,
        pnlcomm: 0.9,
        reason: 'take_profit',
        hold_minutes: 30,
        hold_bars: 6,
      },
    ],
    error: null,
  }
}

const selection: BacktestSelectionSummary = {
  start_date: '2024-01-02',
  end_date: '2024-01-02',
  resolution: '1m',
  feed: 'iex',
  symbols: ['AAPL'],
  triggers: ['trend'],
  exit_rules: ['profit_target'],
}

beforeEach(() => {
  useSettingsMock.mockReturnValue({
    platformSettings: {
      ...defaultPlatformSettings,
      platform_behavior: {
        ...defaultPlatformSettings.platform_behavior,
        timezone: 'UTC',
        time_display_format: '24h',
      },
    },
    appearance: {
      time_display_format: '24h',
    },
  })
})

afterEach(() => {
  cleanup()
})

describe('BacktestRunDetailPanel', () => {
  it('switches to the chart tab and forwards the trade focus window', async () => {
    const { getByRole, getByTestId } = render(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter>
          <BacktestRunDetailPanel backtestId="backtest-1" result={makeResult()} selection={selection} />
        </MemoryRouter>
      </ThemeProvider>,
    )

    const tablist = getByRole('tablist')
    fireEvent.click(within(tablist).getByRole('tab', { name: /trades/i }))
    fireEvent.click(getByRole('button', { name: /open chart for trade/i }))

    await waitFor(() =>
      expect(getByRole('tab', { name: /chart/i })).toHaveAttribute('aria-selected', 'true'),
    )

    expect(getByTestId('chart-focus')).toHaveTextContent(
      `${Date.parse('2024-01-02T09:50:00.000Z')}:${Date.parse('2024-01-02T10:40:00.000Z')}`,
    )
  })

  it('clears the trade focus window when the chart is reset', async () => {
    const { getByRole, getByTestId } = render(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter>
          <BacktestRunDetailPanel backtestId="backtest-1" result={makeResult()} selection={selection} />
        </MemoryRouter>
      </ThemeProvider>,
    )

    const tablist = getByRole('tablist')
    fireEvent.click(within(tablist).getByRole('tab', { name: /trades/i }))
    fireEvent.click(getByRole('button', { name: /open chart for trade/i }))

    await waitFor(() =>
      expect(getByRole('tab', { name: /chart/i })).toHaveAttribute('aria-selected', 'true'),
    )

    fireEvent.click(getByRole('button', { name: /reset chart/i }))

    expect(getByTestId('chart-focus')).toHaveTextContent('none')
  })
})
