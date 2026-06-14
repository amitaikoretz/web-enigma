import '@testing-library/jest-dom/vitest'

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

const fetchBacktestsMock = vi.hoisted(() => vi.fn())
const deleteBacktestMock = vi.hoisted(() => vi.fn())
const retryBacktestMock = vi.hoisted(() => vi.fn())
const retryBacktestForceMock = vi.hoisted(() => vi.fn())

vi.mock('../api/backtests', () => ({
  deleteBacktest: deleteBacktestMock,
  fetchBacktests: fetchBacktestsMock,
  retryBacktest: retryBacktestMock,
  retryBacktestForce: retryBacktestForceMock,
}))

vi.mock('../settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      platform_behavior: {
        auto_refresh_interval_seconds: 60,
        timezone: 'UTC',
      },
      backtest_defaults: {
        results_table_columns: ['status'],
      },
    },
    appearance: {
      time_display_format: '24h',
    },
  }),
}))

import { BacktestsListPage } from './BacktestsListPage'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{JSON.stringify({ pathname: location.pathname, state: location.state })}</div>
}

describe('BacktestsListPage', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    fetchBacktestsMock.mockResolvedValue({
      items: [
        {
          id: 'bt-1',
          backtest_type: 'classic',
          created_at: '2026-06-01T12:00:00.000Z',
          updated_at: '2026-06-01T12:01:00.000Z',
          status: 'succeeded',
          selection: null,
        },
        {
          id: 'bt-2',
          backtest_type: 'vectorbt',
          created_at: '2026-06-02T12:00:00.000Z',
          updated_at: '2026-06-02T12:01:00.000Z',
          status: 'succeeded',
          selection: null,
        },
      ],
      total: 2,
    })
  })

  function clickBacktestSelection(backtestId: string) {
    const label = screen.getByLabelText(`Select backtest ${backtestId}`)
    const input = label.querySelector('input')
    if (!input) {
      throw new Error(`Checkbox input not found for ${backtestId}`)
    }
    fireEvent.click(input)
  }

  it('deep-links selected backtests into the risk wizard route', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests']}>
        <Routes>
          <Route path="/backtests" element={<BacktestsListPage />} />
          <Route path="/models/risk/new" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByLabelText('Select backtest bt-1')
    clickBacktestSelection('bt-1')
    fireEvent.click(screen.getByRole('button', { name: /train risk model/i }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/models/risk/new')
    expect(screen.getByTestId('location')).toHaveTextContent('"sourceKind":"backtest"')
    expect(screen.getByTestId('location')).toHaveTextContent('"selectedCount":1')
  })

  it('renders a backtest type column with readable labels', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests']}>
        <Routes>
          <Route path="/backtests" element={<BacktestsListPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByLabelText('Select backtest bt-1')

    expect(screen.getByRole('columnheader', { name: 'Type' })).toBeInTheDocument()
    expect(screen.getByText('Classic')).toBeInTheDocument()
    expect(screen.getByText('Vector bt')).toBeInTheDocument()
  })

  it('deep-links selected backtests into the return forecast wizard route', async () => {
    render(
      <MemoryRouter initialEntries={['/backtests']}>
        <Routes>
          <Route path="/backtests" element={<BacktestsListPage />} />
          <Route path="/models/returns/new" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByLabelText('Select backtest bt-1')
    clickBacktestSelection('bt-1')
    fireEvent.click(screen.getByRole('button', { name: /train return forecast/i }))

    expect(await screen.findByTestId('location')).toHaveTextContent('/models/returns/new')
    expect(screen.getByTestId('location')).toHaveTextContent('"sourceKind":"backtest"')
    expect(screen.getByTestId('location')).toHaveTextContent('"selectedCount":1')
  })
})
