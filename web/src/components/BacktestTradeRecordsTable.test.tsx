import '@testing-library/jest-dom/vitest'

import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/react'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { BacktestTradeRecord } from '../types/backtests'
import { BacktestTradeRecordsTable } from './BacktestTradeRecordsTable'

function makeTrade(day: number, overrides: Partial<BacktestTradeRecord> = {}): BacktestTradeRecord {
  return {
    datetime: `2024-01-${String(day).padStart(2, '0')}T09:30:00.000Z`,
    size: day,
    price: day * 10,
    value: day * 10,
    pnl: day,
    pnlcomm: day - 0.1,
    reason: `exit_${day}`,
    entry_datetime: `2024-01-${String(day).padStart(2, '0')}T09:00:00.000Z`,
    hold_minutes: day * 15,
    hold_bars: day * 3,
    ...overrides,
  }
}

const trades: BacktestTradeRecord[] = [
  makeTrade(1, { reason: 'stop_loss', pnl: -1, pnlcomm: -1.1 }),
  makeTrade(2, { reason: 'take_profit' }),
  makeTrade(3, { reason: 'session_close' }),
  makeTrade(4, { reason: 'trailing_stop' }),
  makeTrade(5),
  makeTrade(6),
  makeTrade(7),
  makeTrade(8),
  makeTrade(9),
  makeTrade(10),
  makeTrade(11),
  makeTrade(12),
]

let mockFetch: ReturnType<typeof vi.fn>

function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location">{location.search}</div>
}

function renderTable(
  initialPath = '/backtests/1',
  onFocusChartTrade = vi.fn(),
  tableTrades: BacktestTradeRecord[] = trades,
  backtestId = 'backtest-1',
  runId = 'run-1',
) {
  return render(
    <ThemeProvider theme={createTheme()}>
      <MemoryRouter initialEntries={[initialPath]}>
        <LocationDisplay />
        <BacktestTradeRecordsTable
          backtestId={backtestId}
          runId={runId}
          trades={tableTrades}
          timezone="UTC"
          timeDisplayFormat="24h"
          onFocusChartTrade={onFocusChartTrade}
        />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

function visibleSizeValues(view: ReturnType<typeof render>) {
  const tables = view.container.querySelectorAll('table')
  const table = tables[tables.length - 1]
  if (!table) {
    throw new Error('trade table not found')
  }
  return within(table)
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).getAllByRole('cell')[1].textContent)
}

function searchInput(view: ReturnType<typeof render>) {
  const input = view.container.querySelector<HTMLInputElement>('input[placeholder="Timestamp, price, PnL, exit reason..."]')
  if (!input) {
    throw new Error('search input not found')
  }
  return input
}

function locationText(view: ReturnType<typeof render>) {
  const nodes = view.container.querySelectorAll<HTMLElement>('[data-testid="location"]')
  if (nodes.length === 0) {
    throw new Error('location marker not found')
  }
  return nodes[nodes.length - 1].textContent ?? ''
}

function locationParams(view: ReturnType<typeof render>) {
  return new URLSearchParams(locationText(view).replace(/^\?/, ''))
}

function clearButton(view: ReturnType<typeof render>) {
  const button = Array.from(view.container.querySelectorAll<HTMLButtonElement>('button')).find(
    (candidate) => candidate.textContent === 'Clear',
  )
  if (!button) {
    throw new Error('clear button not found')
  }
  return button
}

describe('BacktestTradeRecordsTable', () => {
  beforeEach(() => {
    mockFetch = vi.fn()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    })
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('sorts the filtered dataset before paginating it', () => {
    const view = renderTable('/backtests/1?trade_page_size=10')

    expect(visibleSizeValues(view)).toEqual(['1.00', '2.00', '3.00', '4.00', '5.00', '6.00', '7.00', '8.00', '9.00', '10.00'])

    fireEvent.click(view.getByRole('button', { name: /size/i }))

    expect(visibleSizeValues(view)).toEqual(['12.00', '11.00', '10.00', '9.00', '8.00', '7.00', '6.00', '5.00', '4.00', '3.00'])

    fireEvent.click(view.getByLabelText(/go to next page/i))

    expect(visibleSizeValues(view)).toEqual(['2.00', '1.00'])
    expect(locationParams(view).get('trade_page')).toBe('2')
    expect(locationParams(view).get('trade_page_size')).toBe('10')
  })

  it('searches across timestamps, numeric fields, and exit reasons while keeping the URL in sync', () => {
    const view = renderTable('/backtests/1?trade_page=2&trade_page_size=10')

    fireEvent.change(searchInput(view), {
      target: { value: 'take_profit' },
    })

    expect(locationParams(view).get('trade_page')).toBe(null)
    expect(locationParams(view).get('trade_page_size')).toBe('10')
    expect(locationParams(view).get('trade_search')).toBe('take_profit')
    expect(visibleSizeValues(view)).toEqual(['2.00'])

    fireEvent.change(searchInput(view), {
      target: { value: '2024-01-03' },
    })

    expect(locationParams(view).get('trade_page')).toBe(null)
    expect(locationParams(view).get('trade_page_size')).toBe('10')
    expect(locationParams(view).get('trade_search')).toBe('2024-01-03')
    expect(visibleSizeValues(view)).toEqual(['3.00'])

    fireEvent.change(searchInput(view), {
      target: { value: '180' },
    })

    expect(visibleSizeValues(view)).toEqual(['12.00'])
  })

  it('renders the chart action for a row without affecting the table state', () => {
    const view = renderTable('/backtests/1?trade_page=2&trade_page_size=10')

    const chartButtons = view.getAllByRole('button', { name: /open chart for trade/i })
    const chartButton = chartButtons.find((button) => !button.hasAttribute('disabled'))
    expect(chartButton).toBeDefined()
    expect(chartButton).toHaveAttribute('title', 'Show chart for this trade')
    expect(locationParams(view).get('trade_page')).toBe('2')
    expect(locationParams(view).get('trade_page_size')).toBe('10')
  })

  it('disables replay copying when a trade lacks timestamps', () => {
    const view = renderTable('/backtests/1', vi.fn(), [makeTrade(1, { datetime: null, entry_datetime: null })])

    expect(view.getAllByRole('button', { name: /copy replay debug config/i })[0]).toBeDisabled()
  })

  it('copies a replay debug launch configuration for a trade', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })

    mockFetch.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          capsule: {
            capsule_version: 1,
            backtest_id: 'backtest-1',
            run_id: 'run-1',
            run_name: 'run one',
            run_symbol: 'AAPL',
            run_strategy: 'buy_and_hold',
            trade_index: 0,
            target_methods: [
              'app.strategies.implementations.PortableBacktestingStrategy.next',
              'app.strategies.components.ComposableStrategyCore.on_bar',
            ],
            break_at: 'entry',
            trade: trades[0],
            trade_entry_time: trades[0].entry_datetime,
            trade_exit_time: trades[0].datetime,
            focus_window_start: '2024-01-01T08:50:00.000Z',
            focus_window_end: '2024-01-01T09:40:00.000Z',
            config_format: 'yaml',
            config_text: 'runs:\n  - run_id: run-1\n',
            config_sha256: 'abc123',
          },
          launch_config: {
            name: 'Replay trade: backtest-1 / run-1 #1',
            type: 'debugpy',
            request: 'launch',
            python: '${command:python.interpreterPath}',
            module: 'app.cli',
            cwd: '${workspaceFolder}',
            console: 'integratedTerminal',
            env: {
              PYTHONPATH: '${workspaceFolder}/src',
              ALPACA_API_KEY: '${env:ALPACA_API_KEY}',
              ALPACA_SECRET_KEY: '${env:ALPACA_SECRET_KEY}',
            },
            args: ['replay-trade', '--capsule-b64', 'YWJj'],
            justMyCode: true,
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    const view = renderTable('/backtests/1', vi.fn())
    fireEvent.click(view.getAllByRole('button', { name: /copy replay debug config/i })[0])

    expect(mockFetch).toHaveBeenCalledWith('/api/backtests/backtest-1/runs/run-1/trades/0/replay-capsule')
    expect(await view.findByText('Copied replay debug config to clipboard.')).toBeInTheDocument()
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining('"module": "app.cli"'))
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining('"--capsule-b64"'))
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining('"ALPACA_API_KEY": "${env:ALPACA_API_KEY}"'))
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining('"ALPACA_SECRET_KEY": "${env:ALPACA_SECRET_KEY}"'))
    })
  })

  it('shows distinct empty states for no trades and no search matches', () => {
    const emptyRender = render(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter>
          <BacktestTradeRecordsTable
            backtestId="backtest-1"
            runId="run-1"
            trades={[]}
            timezone="UTC"
            timeDisplayFormat="24h"
          />
        </MemoryRouter>
      </ThemeProvider>,
    )

    expect(emptyRender.getByText('No trade records were emitted for this run.')).toBeInTheDocument()
    emptyRender.unmount()

    const searchRender = renderTable('/backtests/1?trade_search=does-not-match')

    expect(searchRender.getByText('No trade records match the current search.')).toBeInTheDocument()
    expect(clearButton(searchRender)).toBeInTheDocument()
  })
})
